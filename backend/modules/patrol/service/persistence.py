from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.core.database.session import Session
from backend.modules.patrol.ai_tasks import (
    frozenset_ai_tasks,
    live_detection_ai_task,
    map_anomaly_to_ai_task,
)
from backend.modules.patrol.repository import PatrolDetectionRepository
from backend.modules.patrol.service.mission_runtime_store import ActiveMissionRuntimeContext
from backend.modules.patrol.vision.models import Detection, FramePacket

log = logging.getLogger(__name__)

RuntimeContextProvider = Callable[[], Awaitable[ActiveMissionRuntimeContext | None]]


@dataclass(frozen=True)
class PersistedAnomalyResult:
    flight_id: int
    detection_id: int
    incident_id: int
    incident_created: bool
    alert_id: int | None
    mission_task_type: str
    ai_task: str


class PatrolPersistenceService:
    def __init__(
        self,
        *,
        runtime_context_provider: RuntimeContextProvider,
        repo: PatrolDetectionRepository | None = None,
    ) -> None:
        self._runtime_context_provider = runtime_context_provider
        self._repo = repo or PatrolDetectionRepository()

    def _infer_patrol_task_type_from_runtime_mission_type(self, mission_type: str) -> str:
        mt = str(mission_type or "").strip().lower()
        if mt in {"private_patrol", "perimeter_patrol"}:
            return "perimeter_patrol"
        if mt in {"private_patrol_waypoint", "waypoint_patrol"}:
            return "waypoint_patrol"
        if mt in {"private_patrol_grid", "grid_surveillance"}:
            return "grid_surveillance"
        if mt in {"private_patrol_event_triggered", "event_triggered_patrol"}:
            return "event_triggered_patrol"
        return ""

    def _allowed_ai_tasks(self, runtime_ctx: ActiveMissionRuntimeContext) -> frozenset[str]:
        return frozenset_ai_tasks(runtime_ctx.ai_tasks or None)

    def _ai_task_allowed(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        allowed_ai_tasks: frozenset[str],
    ) -> tuple[str, bool]:
        label = str(payload.get("label") or "unknown")
        ai_task = map_anomaly_to_ai_task(event_type, label)
        if allowed_ai_tasks and ai_task not in allowed_ai_tasks:
            return ai_task, False
        return ai_task, True

    def _normalize_object_class(self, payload: dict[str, Any]) -> str:
        value = (
            payload.get("object_class")
            or payload.get("label")
            or payload.get("class")
            or payload.get("target_label")
            or "unknown"
        )
        return str(value).strip().lower() or "unknown"

    def _normalize_track_id(self, payload: dict[str, Any]) -> str | None:
        value = payload.get("track_id")
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _extract_bbox(self, payload: dict[str, Any]) -> dict[str, Any]:
        bbox = payload.get("bbox") or payload.get("bbox_xyxy") or {}
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            return {
                "x1": int(bbox[0]),
                "y1": int(bbox[1]),
                "x2": int(bbox[2]),
                "y2": int(bbox[3]),
            }
        if isinstance(bbox, dict):
            return bbox
        return {}

    def _extract_centroid(self, payload: dict[str, Any]) -> dict[str, Any]:
        centroid = payload.get("centroid") or payload.get("centroid_xy") or {}
        if isinstance(centroid, (list, tuple)) and len(centroid) == 2:
            return {"x": int(centroid[0]), "y": int(centroid[1])}
        if isinstance(centroid, dict):
            return centroid

        bbox = self._extract_bbox(payload)
        if {"x1", "y1", "x2", "y2"}.issubset(bbox.keys()):
            return {
                "x": int((int(bbox["x1"]) + int(bbox["x2"])) / 2),
                "y": int((int(bbox["y1"]) + int(bbox["y2"])) / 2),
            }
        return {}

    async def _resolve_active_runtime_context(
        self,
    ) -> ActiveMissionRuntimeContext | None:
        return await self._runtime_context_provider()

    async def persist_anomaly(self, *, anomaly, packet, telemetry, motion_meta):
        runtime_ctx = await self._resolve_active_runtime_context()
        if runtime_ctx is None or runtime_ctx.db_flight_id is None:
            return None

        mission_task_type = (
            runtime_ctx.private_patrol_task_type or runtime_ctx.mission_type or "private_patrol"
        )

        payload = anomaly.payload or {}
        allowed = self._allowed_ai_tasks(runtime_ctx)
        ai_task, allowed_task = self._ai_task_allowed(
            event_type=anomaly.event_type,
            payload=payload,
            allowed_ai_tasks=allowed,
        )
        if not allowed_task:
            return None

        async with Session() as db:
            (
                detection,
                incident,
                created,
                alert,
            ) = await self._repo.persist_detection_pipeline_result(
                db,
                flight_id=int(runtime_ctx.db_flight_id),
                mission_task_type=mission_task_type,
                ai_task=ai_task,
                object_class=str(payload.get("label") or "unknown"),
                confidence=float(anomaly.confidence),
                bbox_xyxy=payload.get("bbox") or {},
                centroid_xy=payload.get("centroid_xy") or {},
                anomaly_type=anomaly.event_type,
                track_id=str(payload["track_id"]) if payload.get("track_id") is not None else None,
                zone_name=self._extract_zone_name(payload),
                checkpoint_index=payload.get("checkpoint_index"),
                frame_id=getattr(packet, "frame_id", None),
                lat=(anomaly.location.lat if anomaly.location else None),
                lon=(anomaly.location.lon if anomaly.location else None),
                alt=telemetry.get("altitude_m"),
                heading=telemetry.get("heading"),
                groundspeed=telemetry.get("groundspeed"),
                source=str(payload.get("source") or "rgb"),
                snapshot_path=payload.get("snapshot_path"),
                clip_path=payload.get("clip_path"),
                model_name=payload.get("model_name"),
                model_version=payload.get("model_version"),
                meta_data={
                    **payload,
                    "motion_meta": motion_meta or {},
                    "runtime_client_flight_id": runtime_ctx.client_flight_id,
                },
            )
            await db.commit()

        if created:
            from backend.modules.agents.hooks import schedule_patrol_incident_summary

            schedule_patrol_incident_summary(incident_id=int(incident.id), created=True)

        return PersistedAnomalyResult(
            flight_id=int(runtime_ctx.db_flight_id),
            detection_id=detection.id,
            incident_id=incident.id,
            incident_created=created,
            alert_id=(alert.id if alert else None),
            mission_task_type=mission_task_type,
            ai_task=ai_task,
        )

    async def persist_live_detections(
        self,
        *,
        detections: list[Detection],
        packet: FramePacket,
        telemetry: dict[str, Any],
        model_name: str,
    ) -> None:
        runtime_ctx = await self._resolve_active_runtime_context()
        if runtime_ctx is None or runtime_ctx.db_flight_id is None or not detections:
            return

        mission_task_type = runtime_ctx.mission_type or "live_camera"
        allowed = self._allowed_ai_tasks(runtime_ctx)
        image_height, image_width = packet.image.shape[:2]
        async with Session() as db:
            for detection in detections:
                ai_task = live_detection_ai_task(detection.label, allowed)
                if ai_task is None:
                    continue
                x1, y1, x2, y2 = detection.bbox
                await self._repo.add_patrol_detection(
                    db,
                    flight_id=int(runtime_ctx.db_flight_id),
                    mission_task_type=mission_task_type,
                    ai_task=ai_task,
                    object_class=detection.label,
                    confidence=detection.confidence,
                    bbox_xyxy={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    centroid_xy={"x": (x1 + x2) // 2, "y": (y1 + y2) // 2},
                    frame_id=packet.frame_id,
                    lat=telemetry.get("lat"),
                    lon=telemetry.get("lon"),
                    alt=telemetry.get("altitude_m"),
                    heading=telemetry.get("heading"),
                    groundspeed=telemetry.get("groundspeed"),
                    source="live_object_detection",
                    model_name=model_name,
                    meta_data={
                        "image_width": int(image_width),
                        "image_height": int(image_height),
                        "runtime_client_flight_id": runtime_ctx.client_flight_id,
                    },
                )
            await db.commit()

    def _extract_zone_name(self, payload: dict) -> str | None:
        zones = payload.get("zones")
        if isinstance(zones, list) and zones:
            return str(zones[0])
        zone_name = payload.get("zone_name")
        return str(zone_name) if zone_name else None
