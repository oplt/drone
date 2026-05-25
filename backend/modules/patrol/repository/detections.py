from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.missions.flight_models import FlightEvent
from backend.modules.patrol.models import (
    PatrolDetection,
)


@dataclass(frozen=True)
class PatrolAlertDecision:
    should_alert: bool
    severity: str
    title: str
    message: str
    dedupe_key: str


class PatrolDetectionMixin:
    def utcnow(self) -> datetime:
        return datetime.now(UTC)

    async def add_patrol_detection(
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
    ) -> PatrolDetection:
        row = PatrolDetection(
            flight_id=flight_id,
            telemetry_id=telemetry_id,
            frame_id=frame_id,
            mission_task_type=mission_task_type,
            ai_task=ai_task,
            object_class=object_class,
            anomaly_type=anomaly_type,
            track_id=(str(track_id).strip() if track_id else None),
            zone_name=(str(zone_name).strip() if zone_name else None),
            checkpoint_index=checkpoint_index,
            confidence=float(confidence),
            bbox_xyxy=bbox_xyxy or {},
            centroid_xy=centroid_xy or {},
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
            meta_data=meta_data or {},
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    async def add_detection_summary_event(
        self,
        db: AsyncSession,
        *,
        flight_id: int,
        event_type: str,
        data: dict[str, Any],
    ) -> FlightEvent:
        row = FlightEvent(
            flight_id=flight_id,
            type=event_type,
            data=data or {},
        )
        db.add(row)
        await db.flush()
        return row
