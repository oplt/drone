from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

from backend.ml.patrol.config import ml_settings
from backend.ml.patrol.stream_reader import StreamReader
from backend.ml.patrol.motion import MotionPrefilter
from backend.ml.patrol.detector import ObjectDetector
from backend.ml.patrol.tracker import SimpleTracker
from backend.ml.patrol.geo import GeoProjector
from backend.ml.patrol.zones import Zone, ZoneEngine
from backend.ml.patrol.anomaly import AnomalyScorer
from backend.ml.patrol.events import EventSink
from backend.ml.patrol.evidence import EvidenceRecorder
from backend.services.patrol.patrol_persistence import PatrolPersistenceService
from backend.services.patrol.mission_runtime_store import mission_runtime_store

try:
    from backend.services.patrol.patrol_persistence import PatrolPersistenceService
except Exception:
    PatrolPersistenceService = None  # type: ignore

log = logging.getLogger(__name__)
_SENTINEL = object()
_MAX_TELEMETRY_AGE_S = 5.0


class DroneAnomalyPipeline:
    def __init__(self) -> None:
        self.reader: Optional[StreamReader] = None
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

        self.persistence = None if PatrolPersistenceService is None else PatrolPersistenceService(
            runtime_context_provider=mission_runtime_store.get_active_context
        )

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._running = False
        self._started_at: Optional[datetime] = None
        self._last_frame_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._frames_processed = 0
        self._anomalies_emitted = 0
        self._stream_source: str | int | None = ml_settings.stream_source

    async def _read_next_packet(self):
        if self.reader is None:
            raise RuntimeError("Pipeline reader is not initialized. Call start() first.")
        return await asyncio.to_thread(self.reader.read)

    async def start(self, stream_source: Optional[str | int] = None) -> None:
        if self._task and not self._task.done():
            return

        self._stream_source = stream_source or self._stream_source or ml_settings.stream_source
        self.reader = StreamReader(
            source=self._stream_source,
            frame_stride=ml_settings.frame_stride,
        )

        self._stop_event = asyncio.Event()
        self._running = True
        self._started_at = datetime.utcnow()
        self._last_error = None
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
            from backend.messaging.websocket import telemetry_manager
        except Exception:
            return telemetry

        timestamp = self._to_float((telemetry_manager.last_telemetry or {}).get("timestamp"))
        if (
            not telemetry_manager._running
            or timestamp is None
            or (time.time() - timestamp) > _MAX_TELEMETRY_AGE_S
        ):
            return telemetry

        cached = telemetry_manager.last_telemetry or {}
        position = cached.get("position") or {}
        status = cached.get("status") or {}
        camera = cached.get("camera") or {}

        lat = self._to_float(position.get("lat"))
        lon = self._to_float(position.get("lon"))
        altitude_m = self._to_float(position.get("relative_alt"))
        if altitude_m is None or altitude_m <= 0:
            altitude_m = self._to_float(position.get("alt"))

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
                "heading": self._to_float(status.get("heading")),
                "groundspeed": self._to_float(status.get("groundspeed")),
                "gimbal_pitch_deg": self._to_float(camera.get("gimbal_pitch_deg")),
                "timestamp": timestamp,
                "has_position": lat is not None and lon is not None and altitude_m is not None,
            }
        )
        return telemetry

    async def _next_packet(self, iterator):
        return await asyncio.to_thread(next, iterator, _SENTINEL)


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

                should_run = True
                motion_meta: dict[str, Any] = {}

                if ml_settings.enable_motion_prefilter:
                    should_run, motion_meta = await asyncio.to_thread(
                        self.motion.has_motion,
                        packet,
                    )

                if not should_run:
                    await asyncio.sleep(0)
                    continue

                detections = await asyncio.to_thread(self.detector.detect, packet)
                tracks = self.tracker.update(detections, packet.ts)

                gps_lookup: dict[int, Any] = {}
                telemetry = self._get_latest_telemetry()

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
                    if ml_settings.save_debug_frames:
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
                        await self.events.send(anomaly)
                    except Exception as e:
                        log.exception("Failed to dispatch anomaly")
                        self._last_error = str(e)

                    self._anomalies_emitted += 1

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
