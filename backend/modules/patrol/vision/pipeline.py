from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from backend.modules.patrol.service.mission_runtime_store import mission_runtime_store
from backend.modules.patrol.vision.anomaly import AnomalyScorer
from backend.modules.patrol.ai_tasks import (
    PATROL_AI_TASKS,
    apply_active_ai_tasks,
    frozenset_ai_tasks,
    live_detection_ai_task,
    map_anomaly_to_ai_task,
    yolo_detection_enabled,
)
from backend.modules.patrol.vision.config import ml_settings
from backend.modules.patrol.vision.evidence_policy import should_save_evidence_snapshot
from backend.modules.patrol.vision.detector import ObjectDetector
from backend.modules.patrol.vision.events import EventDispatcher, EventSink, PipelineEvent
from backend.modules.patrol.vision.evidence import EvidenceRecorder
from backend.modules.patrol.vision.geo import GeoProjector
from backend.modules.patrol.vision.live_detections import LiveDetectionSampler
from backend.modules.patrol.vision.models import AnomalyEvent, FramePacket, GeoPoint
from backend.modules.patrol.vision.motion import MotionPrefilter
from backend.modules.patrol.vision.stream_reader import FrameReader, create_stream_reader
from backend.modules.patrol.vision.tracker import SimpleTracker
from backend.modules.patrol.vision.zones import Zone, ZoneEngine

try:
    from backend.modules.patrol.service.persistence import PatrolPersistenceService
except Exception:
    PatrolPersistenceService = None  # type: ignore

log = logging.getLogger(__name__)
_MAX_TELEMETRY_AGE_S = 5.0


class DroneAnomalyPipeline:
    def __init__(self) -> None:
        self.reader: FrameReader | None = None
        self.motion = MotionPrefilter(min_motion_area=ml_settings.min_motion_area)
        self.detector = ObjectDetector(
            model_path=ml_settings.detector_model_path,
            conf=ml_settings.detector_conf,
            iou=ml_settings.detector_iou,
        )
        self.tracker = SimpleTracker()
        self.geo = GeoProjector()
        self.events = EventSink(
            mode=getattr(ml_settings, "event_sink_mode", "noop"),
            url=getattr(ml_settings, "event_sink_url", None),
        )
        self.event_dispatcher = EventDispatcher(
            emit_websocket_events=ml_settings.emit_websocket_events,
            duplicate_window_s=ml_settings.max_duplicate_event_s,
            max_events_per_track=ml_settings.max_events_per_track,
        )
        self.evidence = EvidenceRecorder(ml_settings.evidence_dir)

        self.zone_engine = ZoneEngine(
            zones=[
                Zone(
                    name="gate",
                    polygon=[
                        (50.0, 4.0),
                        (50.0, 4.001),
                        (50.001, 4.001),
                        (50.001, 4.0),
                    ],
                    restricted=True,
                )
            ]
        )
        self.anomaly = AnomalyScorer(
            zone_engine=self.zone_engine,
            loitering_seconds=ml_settings.loitering_seconds,
        )

        self.persistence = (
            None
            if PatrolPersistenceService is None
            else PatrolPersistenceService(
                runtime_context_provider=mission_runtime_store.get_active_context
            )
        )

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._running = False
        self._started_at: datetime | None = None
        self._last_frame_at: datetime | None = None
        self._last_error: str | None = None
        self._frames_processed = 0
        self._anomalies_emitted = 0
        self._stream_source: str | int | None = ml_settings.stream_source
        self.live_detections = LiveDetectionSampler(ml_settings.live_detection_persist_interval_s)
        self.active_ai_tasks: frozenset[str] = frozenset(PATROL_AI_TASKS)
        self._last_motion_event_at: datetime | None = None
        self.set_active_ai_tasks(list(PATROL_AI_TASKS))

    def set_active_ai_tasks(self, ai_tasks: list[str] | None) -> None:
        self.active_ai_tasks = apply_active_ai_tasks(
            enabled_tasks=ai_tasks,
            detector=self.detector,
            anomaly_scorer=self.anomaly,
        )

    async def _read_next_packet(self):
        if self.reader is None:
            raise RuntimeError("Pipeline reader is not initialized. Call start() first.")
        return await asyncio.to_thread(self.reader.read)

    async def start(
        self,
        stream_source: str | int | None = None,
        ai_tasks: list[str] | None = None,
    ) -> None:
        if self._task and not self._task.done():
            if ai_tasks is not None:
                self.set_active_ai_tasks(ai_tasks)
            return

        self.set_active_ai_tasks(ai_tasks)
        self._stream_source = stream_source or self._stream_source or ml_settings.stream_source
        self.reader = create_stream_reader(
            self._stream_source,
            frame_stride=ml_settings.frame_stride,
        )

        self._stop_event = asyncio.Event()
        self._running = True
        self._started_at = datetime.utcnow()
        self._last_error = None
        self._last_motion_event_at = None
        self.live_detections.reset()
        self._task = asyncio.create_task(self.run_forever(), name="drone-anomaly-pipeline")

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running and self._task is not None and not self._task.done(),
            "stream_source": self._stream_source,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_frame_at": self._last_frame_at.isoformat() if self._last_frame_at else None,
            "last_error": self._last_error,
            "frames_processed": self._frames_processed,
            "anomalies_emitted": self._anomalies_emitted,
            "detections": self.live_detections.current(),
            "active_ai_tasks": sorted(self.active_ai_tasks),
        }

    def set_zones(self, zones: list[dict[str, Any]]) -> None:
        normalized: list[Zone] = []
        for zone in zones:
            polygon_points = []
            for point in zone.get("polygon") or []:
                try:
                    polygon_points.append((float(point["lat"]), float(point["lon"])))
                except (KeyError, TypeError, ValueError):
                    continue
            if len(polygon_points) < 3:
                continue
            normalized.append(
                Zone(
                    name=str(zone.get("name") or f"zone-{len(normalized) + 1}"),
                    polygon=polygon_points,
                    restricted=bool(zone.get("restricted", True)),
                )
            )

        self.zone_engine.set_zones(normalized)
        self.anomaly.zone_engine = self.zone_engine

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_latest_telemetry(self) -> dict[str, Any]:
        telemetry: dict[str, Any] = {
            "id": None,
            "lat": None,
            "lon": None,
            "altitude_m": None,
            "heading": None,
            "groundspeed": None,
            "gimbal_pitch_deg": None,
            "timestamp": None,
            "has_position": False,
        }

        try:
            from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
        except Exception:
            return telemetry

        telemetry_envelope = telemetry_manager.get_last_telemetry_envelope()
        if telemetry_envelope is None:
            return telemetry

        timestamp = self._to_float(telemetry_envelope.emitted_at.timestamp())
        runtime = telemetry_manager.runtime_snapshot()
        if (
            not runtime["running"]
            or timestamp is None
            or (time.time() - timestamp) > _MAX_TELEMETRY_AGE_S
        ):
            return telemetry

        payload = telemetry_envelope.payload

        lat = self._to_float(payload.position.lat)
        lon = self._to_float(payload.position.lon)
        altitude_m = self._to_float(payload.position.relative_alt_m)
        if altitude_m is None or altitude_m <= 0:
            altitude_m = self._to_float(payload.position.alt_m)

        if lat is not None and not (-90.0 <= lat <= 90.0):
            lat = None
        if lon is not None and not (-180.0 <= lon <= 180.0):
            lon = None
        if lat == 0.0 and lon == 0.0:
            lat = None
            lon = None
        if altitude_m is not None and altitude_m <= 0:
            altitude_m = None

        telemetry.update(
            {
                "lat": lat,
                "lon": lon,
                "altitude_m": altitude_m,
                "heading": self._to_float(payload.motion.heading_deg),
                "groundspeed": self._to_float(payload.motion.groundspeed_mps),
                "gimbal_pitch_deg": self._to_float(payload.camera.gimbal_pitch_deg),
                "timestamp": timestamp,
                "has_position": lat is not None and lon is not None and altitude_m is not None,
            }
        )
        return telemetry

    async def _emit_anomaly(
        self,
        *,
        anomaly: AnomalyEvent,
        packet: FramePacket,
        telemetry: dict[str, Any],
        motion_meta: dict[str, Any],
    ) -> None:
        if await should_save_evidence_snapshot(save_debug_frames=ml_settings.save_debug_frames):
            snapshot = self.evidence.save_frame(packet.image, prefix=anomaly.event_type)
            anomaly.payload["snapshot_path"] = snapshot

        anomaly.payload["frame_id"] = packet.frame_id
        anomaly.payload["motion_meta"] = motion_meta

        if self.persistence is not None:
            try:
                persisted = await self.persistence.persist_anomaly(
                    anomaly=anomaly,
                    packet=packet,
                    telemetry=telemetry,
                    motion_meta=motion_meta,
                )
                if persisted is not None:
                    anomaly.payload["persistence"] = {
                        "flight_id": persisted.flight_id,
                        "detection_id": persisted.detection_id,
                        "incident_id": persisted.incident_id,
                        "incident_created": persisted.incident_created,
                        "alert_id": persisted.alert_id,
                        "mission_task_type": persisted.mission_task_type,
                        "ai_task": persisted.ai_task,
                    }
            except Exception as e:
                log.exception("Failed to persist anomaly")
                self._last_error = str(e)

        try:
            await self.event_dispatcher.dispatch(
                PipelineEvent(
                    event_type=anomaly.event_type,
                    confidence=float(anomaly.confidence),
                    location=(
                        {"lat": anomaly.location.lat, "lon": anomaly.location.lon}
                        if anomaly.location is not None
                        else None
                    ),
                    payload=dict(anomaly.payload or {}),
                )
            )
        except Exception as e:
            log.exception("Failed to broadcast anomaly event")
            self._last_error = str(e)

        if self.events.mode == "http":
            try:
                await self.events.send(anomaly)
            except Exception as e:
                log.exception("Failed to dispatch anomaly to HTTP event sink")
                self._last_error = str(e)

        self._anomalies_emitted += 1

    async def run_forever(self) -> None:
        if self.reader is None:
            raise RuntimeError("Pipeline reader is not initialized. Call start() first.")

        try:
            while not self._stop_event.is_set():
                packet = await self._read_next_packet()

                if packet is None:
                    await asyncio.sleep(0.05)
                    continue

                self._frames_processed += 1
                self._last_frame_at = packet.ts

                motion_meta: dict[str, Any] = {}
                has_motion = False

                if ml_settings.enable_motion_prefilter:
                    has_motion, motion_meta = await asyncio.to_thread(
                        self.motion.has_motion,
                        packet,
                    )

                telemetry = self._get_latest_telemetry()

                if (
                    has_motion
                    and "motion_detection" in self.active_ai_tasks
                    and telemetry.get("lat") is not None
                    and telemetry.get("lon") is not None
                ):
                    now = datetime.utcnow()
                    if (
                        self._last_motion_event_at is None
                        or (now - self._last_motion_event_at).total_seconds()
                        >= ml_settings.max_duplicate_event_s
                    ):
                        motion_anomaly = AnomalyEvent(
                            event_type="scene_motion",
                            confidence=min(
                                0.95,
                                max(
                                    0.50,
                                    float(motion_meta.get("max_motion_area", 0.0))
                                    / float(ml_settings.min_motion_area),
                                ),
                            ),
                            location=GeoPoint(
                                lat=float(telemetry["lat"]),
                                lon=float(telemetry["lon"]),
                            ),
                            payload={
                                "source": "motion_prefilter",
                                "motion_meta": motion_meta,
                            },
                        )
                        await self._emit_anomaly(
                            anomaly=motion_anomaly,
                            packet=packet,
                            telemetry=telemetry,
                            motion_meta=motion_meta,
                        )
                        self._last_motion_event_at = now

                detections = []
                tracks = []
                if yolo_detection_enabled(self.active_ai_tasks):
                    detections = await asyncio.to_thread(self.detector.detect, packet)
                    tracks = self.tracker.update(detections, packet.ts)

                gps_lookup: dict[int, Any] = {}

                try:
                    await self.live_detections.capture(
                        detections=detections,
                        packet=packet,
                        telemetry=telemetry,
                        model_name=ml_settings.detector_model_path,
                        persistence=self.persistence,
                    )
                except Exception as e:
                    log.exception("Failed to persist live object detections")
                    self._last_error = str(e)

                drone_lat = telemetry.get("lat")
                drone_lon = telemetry.get("lon")
                altitude_m = telemetry.get("altitude_m")
                gimbal_pitch_deg = telemetry.get("gimbal_pitch_deg")
                heading_deg = telemetry.get("heading")

                if drone_lat is not None and drone_lon is not None and altitude_m is not None:
                    for track in tracks:
                        gps_lookup[track.track_id] = self.geo.estimate_ground_point(
                            centroid_px=track.centroid,
                            drone_lat=drone_lat,
                            drone_lon=drone_lon,
                            altitude_m=altitude_m,
                            gimbal_pitch_deg=0.0 if gimbal_pitch_deg is None else gimbal_pitch_deg,
                            heading_deg=0.0 if heading_deg is None else heading_deg,
                            image_shape=getattr(packet.image, "shape", None),
                        )

                anomalies = self.anomaly.score(
                    tracks=tracks,
                    gps_lookup=gps_lookup,
                    now=datetime.utcnow(),
                )

                for anomaly in anomalies:
                    await self._emit_anomaly(
                        anomaly=anomaly,
                        packet=packet,
                        telemetry=telemetry,
                        motion_meta=motion_meta,
                    )

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            log.info("DroneAnomalyPipeline cancelled")
            raise
        except Exception as e:
            self._last_error = str(e)
            log.exception("DroneAnomalyPipeline crashed")
            raise
        finally:
            self._running = False
            if self.reader is not None:
                await asyncio.to_thread(self.reader.close)
