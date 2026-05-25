from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.patrol.models import (
    PatrolDetection,
    PatrolIncident,
    PatrolIncidentDetection,
)


@dataclass(frozen=True)
class PatrolAlertDecision:
    should_alert: bool
    severity: str
    title: str
    message: str
    dedupe_key: str


class PatrolIncidentMixin:
    async def _find_candidate_open_incident(
        self,
        db: AsyncSession,
        *,
        detection: PatrolDetection,
        window_seconds: int = 45,
    ) -> PatrolIncident | None:
        cutoff = self.utcnow() - timedelta(seconds=window_seconds)
        incident_type = detection.anomaly_type or f"{detection.object_class}_detected"

        base_filters = [
            PatrolIncident.flight_id == detection.flight_id,
            PatrolIncident.status.in_(("open", "monitoring")),
            PatrolIncident.incident_type == incident_type,
            PatrolIncident.mission_task_type == detection.mission_task_type,
            PatrolIncident.opened_at >= cutoff,
        ]

        if detection.track_id:
            stmt = (
                select(PatrolIncident)
                .where(
                    *base_filters,
                    PatrolIncident.primary_track_id == detection.track_id,
                    PatrolIncident.zone_name == detection.zone_name,
                    PatrolIncident.checkpoint_index == detection.checkpoint_index,
                )
                .order_by(desc(PatrolIncident.updated_at), desc(PatrolIncident.id))
                .limit(1)
            )
            match = await db.scalar(stmt)
            if match is not None:
                return match

        stmt = (
            select(PatrolIncident)
            .where(
                *base_filters,
                PatrolIncident.primary_track_id.is_(None),
                PatrolIncident.primary_object_class == detection.object_class,
                PatrolIncident.zone_name == detection.zone_name,
                PatrolIncident.checkpoint_index == detection.checkpoint_index,
            )
            .order_by(desc(PatrolIncident.updated_at), desc(PatrolIncident.id))
            .limit(1)
        )
        return await db.scalar(stmt)

    async def _link_incident_detection(
        self,
        db: AsyncSession,
        *,
        incident_id: int,
        detection_id: int,
    ) -> None:
        exists = await db.scalar(
            select(PatrolIncidentDetection).where(
                PatrolIncidentDetection.incident_id == incident_id,
                PatrolIncidentDetection.detection_id == detection_id,
            )
        )
        if exists is None:
            db.add(
                PatrolIncidentDetection(
                    incident_id=incident_id,
                    detection_id=detection_id,
                )
            )
            await db.flush()

    async def upsert_patrol_incident(
        self,
        db: AsyncSession,
        *,
        detection: PatrolDetection,
        incident_summary: dict[str, Any] | None = None,
        window_seconds: int = 45,
    ) -> tuple[PatrolIncident, bool]:
        incident = await self._find_candidate_open_incident(
            db,
            detection=detection,
            window_seconds=window_seconds,
        )
        created = False
        incident_type = detection.anomaly_type or f"{detection.object_class}_detected"

        if incident is None:
            incident = PatrolIncident(
                flight_id=detection.flight_id,
                mission_task_type=detection.mission_task_type,
                incident_type=incident_type,
                primary_object_class=detection.object_class,
                primary_track_id=detection.track_id,
                ai_task=detection.ai_task,
                zone_name=detection.zone_name,
                checkpoint_index=detection.checkpoint_index,
                start_lat=detection.lat,
                start_lon=detection.lon,
                end_lat=detection.lat,
                end_lon=detection.lon,
                peak_confidence=detection.confidence,
                detection_count=1,
                first_detection_id=detection.id,
                last_detection_id=detection.id,
                snapshot_path=detection.snapshot_path,
                clip_path=detection.clip_path,
                summary=incident_summary or {},
                status="open",
            )
            db.add(incident)
            await db.flush()
            created = True
        else:
            incident.updated_at = self.utcnow()
            incident.end_lat = detection.lat if detection.lat is not None else incident.end_lat
            incident.end_lon = detection.lon if detection.lon is not None else incident.end_lon
            incident.peak_confidence = max(
                float(incident.peak_confidence or 0.0),
                float(detection.confidence),
            )
            incident.detection_count = int(incident.detection_count or 0) + 1
            incident.last_detection_id = detection.id
            if detection.snapshot_path:
                incident.snapshot_path = detection.snapshot_path
            if detection.clip_path:
                incident.clip_path = detection.clip_path
            incident.summary = {**(incident.summary or {}), **(incident_summary or {})}
            await db.flush()

        await self._link_incident_detection(
            db,
            incident_id=incident.id,
            detection_id=detection.id,
        )
        return incident, created
