from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.alerts.models import OperationalAlert
from backend.modules.patrol.models import (
    PatrolDetection,
    PatrolIncident,
)


@dataclass(frozen=True)
class PatrolAlertDecision:
    should_alert: bool
    severity: str
    title: str
    message: str
    dedupe_key: str


class PatrolPipelineMixin:
    async def persist_detection_pipeline_result(
        self,
        db: AsyncSession,
        *,
        flight_id: int,
        mission_task_type: str,
        ai_task: str,
        object_class: str,
        confidence: float,
        bbox_xyxy: dict[str, Any],
        centroid_xy: dict[str, Any],
        anomaly_type: str | None = None,
        track_id: str | None = None,
        zone_name: str | None = None,
        checkpoint_index: int | None = None,
        telemetry_id: int | None = None,
        frame_id: int | None = None,
        lat: float | None = None,
        lon: float | None = None,
        alt: float | None = None,
        heading: float | None = None,
        groundspeed: float | None = None,
        source: str = "rgb",
        snapshot_path: str | None = None,
        clip_path: str | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
        meta_data: dict[str, Any] | None = None,
    ) -> tuple[PatrolDetection, PatrolIncident, bool, OperationalAlert | None]:
        detection = await self.add_patrol_detection(
            db,
            flight_id=flight_id,
            mission_task_type=mission_task_type,
            ai_task=ai_task,
            object_class=object_class,
            confidence=confidence,
            bbox_xyxy=bbox_xyxy,
            centroid_xy=centroid_xy,
            anomaly_type=anomaly_type,
            track_id=track_id,
            zone_name=zone_name,
            checkpoint_index=checkpoint_index,
            telemetry_id=telemetry_id,
            frame_id=frame_id,
            lat=lat,
            lon=lon,
            alt=alt,
            heading=heading,
            groundspeed=groundspeed,
            source=source,
            snapshot_path=snapshot_path,
            clip_path=clip_path,
            model_name=model_name,
            model_version=model_version,
            meta_data=meta_data,
        )

        incident, created = await self.upsert_patrol_incident(
            db,
            detection=detection,
            incident_summary={
                "source": source,
                "model_name": model_name,
                "model_version": model_version,
            },
        )

        alert = await self.upsert_operational_alert_for_incident(
            db,
            incident=incident,
            detection=detection,
        )

        await self.add_detection_summary_event(
            db,
            flight_id=flight_id,
            event_type=("patrol_incident_opened" if created else "patrol_incident_updated"),
            data={
                "incident_id": incident.id,
                "detection_id": detection.id,
                "incident_type": incident.incident_type,
                "mission_task_type": incident.mission_task_type,
                "object_class": detection.object_class,
                "track_id": detection.track_id,
                "zone_name": detection.zone_name,
                "checkpoint_index": detection.checkpoint_index,
                "confidence": detection.confidence,
                "alert_id": alert.id if alert else None,
            },
        )

        return detection, incident, created, alert
