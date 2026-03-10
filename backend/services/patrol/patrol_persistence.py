from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from backend.db.session import Session
from backend.db.repository.patrol_repo import PatrolDetectionRepository
from typing import Awaitable, Callable, Optional, Any
from backend.services.patrol.mission_runtime_store import ActiveMissionRuntimeContext

log = logging.getLogger(__name__)

RuntimeContextProvider = Callable[[], Awaitable[Optional[ActiveMissionRuntimeContext]]]


@dataclass(frozen=True)
class PersistedAnomalyResult:
    flight_id: int
    detection_id: int
    incident_id: int
    incident_created: bool
    alert_id: Optional[int]
    mission_task_type: str
    ai_task: str


class PatrolPersistenceService:
    def __init__(
            self,
            *,
            runtime_context_provider: RuntimeContextProvider,
            repo: Optional[PatrolDetectionRepository] = None,
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

    def _normalize_ai_task(
            self,
            *,
            anomaly_type: str,
            object_class: str,
            payload: dict[str, Any],
            allowed_ai_tasks: list[str],
    ) -> str:
        explicit = str(payload.get("ai_task") or "").strip()
        if explicit:
            return explicit

        event_type = anomaly_type.strip().lower()
        obj = object_class.strip().lower()

        if event_type in {"restricted_zone_entry", "intrusion_detected", "loitering"}:
            guessed = "vehicle_detection" if obj in {"car", "truck", "bus", "motorcycle", "bicycle"} else "intruder_detection"
        elif event_type in {"fence_line_crossing", "fence_breach", "fence_breach_detected"}:
            guessed = "fence_breach_detection"
        elif event_type in {"scene_motion", "motion_detected"}:
            guessed = "motion_detection"
        else:
            guessed = "vehicle_detection" if obj in {"car", "truck", "bus", "motorcycle", "bicycle"} else "intruder_detection"

        if allowed_ai_tasks and guessed not in allowed_ai_tasks:
            return allowed_ai_tasks[0]
        return guessed

    def _normalize_object_class(self, payload: dict[str, Any]) -> str:
        value = (
                payload.get("object_class")
                or payload.get("label")
                or payload.get("class")
                or payload.get("target_label")
                or "unknown"
        )
        return str(value).strip().lower() or "unknown"

    def _normalize_track_id(self, payload: dict[str, Any]) -> Optional[str]:
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



    async def _resolve_active_runtime_context(self) -> Optional[ActiveMissionRuntimeContext]:
        return await self._runtime_context_provider()


    async def persist_anomaly(self, *, anomaly, packet, telemetry, motion_meta):
        runtime_ctx = await self._resolve_active_runtime_context()
        if runtime_ctx is None or runtime_ctx.db_flight_id is None:
            return None

        mission_task_type = (
                runtime_ctx.private_patrol_task_type
                or runtime_ctx.mission_type
                or "private_patrol"
        )

        payload = anomaly.payload or {}
        ai_task = self._map_ai_task(anomaly.event_type, payload)

        async with Session() as db:
            detection, incident, created, alert = await self._repo.persist_detection_pipeline_result(
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

        return PersistedAnomalyResult(
            flight_id=int(runtime_ctx.db_flight_id),
            detection_id=detection.id,
            incident_id=incident.id,
            incident_created=created,
            alert_id=(alert.id if alert else None),
            mission_task_type=mission_task_type,
            ai_task=ai_task,
        )

    def _map_ai_task(self, event_type: str, payload: dict) -> str:
        label = str(payload.get("label") or "").lower()
        if event_type in {"intrusion_detected", "loitering"}:
            return "intruder_detection"
        if event_type == "restricted_zone_entry" and label in {"car", "truck", "motorcycle", "bicycle"}:
            return "vehicle_detection"
        if event_type == "restricted_zone_entry":
            return "fence_breach_detection"
        if event_type == "scene_motion":
            return "motion_detection"
        return "intruder_detection"

    def _extract_zone_name(self, payload: dict) -> Optional[str]:
        zones = payload.get("zones")
        if isinstance(zones, list) and zones:
            return str(zones[0])
        zone_name = payload.get("zone_name")
        return str(zone_name) if zone_name else None