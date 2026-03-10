from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    FlightEvent,
    OperationalAlert,
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


class PatrolDetectionRepository:
    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

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
            anomaly_type: Optional[str] = None,
            track_id: Optional[str] = None,
            zone_name: Optional[str] = None,
            checkpoint_index: Optional[int] = None,
            telemetry_id: Optional[int] = None,
            frame_id: Optional[int] = None,
            lat: Optional[float] = None,
            lon: Optional[float] = None,
            alt: Optional[float] = None,
            heading: Optional[float] = None,
            groundspeed: Optional[float] = None,
            source: str = "rgb",
            snapshot_path: Optional[str] = None,
            clip_path: Optional[str] = None,
            model_name: Optional[str] = None,
            model_version: Optional[str] = None,
            meta_data: Optional[dict[str, Any]] = None,
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

    async def _find_candidate_open_incident(
            self,
            db: AsyncSession,
            *,
            detection: PatrolDetection,
            window_seconds: int = 45,
    ) -> Optional[PatrolIncident]:
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
            incident_summary: Optional[dict[str, Any]] = None,
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

    def decide_alert_for_incident(
            self,
            *,
            incident: PatrolIncident,
            detection: PatrolDetection,
    ) -> PatrolAlertDecision:
        incident_type = incident.incident_type
        if incident_type in {"restricted_zone_entry", "fence_line_crossing"}:
            severity = "critical"
        elif incident_type in {"intrusion_detected", "loitering"}:
            severity = "high"
        elif incident_type in {"vehicle_detected", "scene_motion"}:
            severity = "medium"
        else:
            severity = "low"

        should_alert = (
                incident.detection_count >= 3
                or incident_type in {"restricted_zone_entry", "fence_line_crossing"}
                or float(incident.peak_confidence or 0.0) >= 0.90
        )

        zone_part = (
                incident.zone_name
                or (f"checkpoint-{incident.checkpoint_index}" if incident.checkpoint_index is not None else "general")
        )
        track_part = incident.primary_track_id or "no-track"

        title = incident_type.replace("_", " ").title()
        message = (
                f"{detection.object_class} detected during {incident.mission_task_type}"
                + (f" in zone '{incident.zone_name}'" if incident.zone_name else "")
                + (f" at checkpoint {incident.checkpoint_index}" if incident.checkpoint_index is not None else "")
        )
        dedupe_key = f"patrol:{incident.flight_id}:{incident.incident_type}:{zone_part}:{track_part}"

        return PatrolAlertDecision(
            should_alert=should_alert,
            severity=severity,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
        )

    async def upsert_operational_alert_for_incident(
            self,
            db: AsyncSession,
            *,
            incident: PatrolIncident,
            detection: PatrolDetection,
    ) -> Optional[OperationalAlert]:
        decision = self.decide_alert_for_incident(incident=incident, detection=detection)
        if not decision.should_alert:
            return None

        now = self.utcnow()
        alert = await db.scalar(
            select(OperationalAlert).where(
                OperationalAlert.dedupe_key == decision.dedupe_key,
                OperationalAlert.status == "open",
                )
        )

        payload = {
            "flight_id": incident.flight_id,
            "incident_id": incident.id,
            "incident_type": incident.incident_type,
            "mission_task_type": incident.mission_task_type,
            "primary_track_id": incident.primary_track_id,
            "object_class": incident.primary_object_class,
            "zone_name": incident.zone_name,
            "checkpoint_index": incident.checkpoint_index,
            "peak_confidence": incident.peak_confidence,
            "detection_count": incident.detection_count,
            "snapshot_path": incident.snapshot_path,
            "clip_path": incident.clip_path,
        }

        if alert is None:
            alert = OperationalAlert(
                rule_type="patrol_incident",
                dedupe_key=decision.dedupe_key,
                source="drone_ml",
                severity=decision.severity,
                status="open",
                title=decision.title,
                message=decision.message,
                meta_data=payload,
                first_triggered_at=now,
                last_triggered_at=now,
                occurrences=1,
            )
            db.add(alert)
            await db.flush()
        else:
            alert.last_triggered_at = now
            alert.occurrences = int(alert.occurrences or 0) + 1
            alert.severity = decision.severity
            alert.title = decision.title
            alert.message = decision.message
            alert.meta_data = payload
            await db.flush()

        incident.last_alert_id = alert.id
        await db.flush()
        return alert

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
            anomaly_type: Optional[str] = None,
            track_id: Optional[str] = None,
            zone_name: Optional[str] = None,
            checkpoint_index: Optional[int] = None,
            telemetry_id: Optional[int] = None,
            frame_id: Optional[int] = None,
            lat: Optional[float] = None,
            lon: Optional[float] = None,
            alt: Optional[float] = None,
            heading: Optional[float] = None,
            groundspeed: Optional[float] = None,
            source: str = "rgb",
            snapshot_path: Optional[str] = None,
            clip_path: Optional[str] = None,
            model_name: Optional[str] = None,
            model_version: Optional[str] = None,
            meta_data: Optional[dict[str, Any]] = None,
    ) -> tuple[PatrolDetection, PatrolIncident, bool, Optional[OperationalAlert]]:
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