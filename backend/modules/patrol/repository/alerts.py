from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
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


class PatrolAlertMixin:
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

        zone_part = incident.zone_name or (
            f"checkpoint-{incident.checkpoint_index}"
            if incident.checkpoint_index is not None
            else "general"
        )
        track_part = incident.primary_track_id or "no-track"

        title = incident_type.replace("_", " ").title()
        message = (
            f"{detection.object_class} detected during {incident.mission_task_type}"
            + (f" in zone '{incident.zone_name}'" if incident.zone_name else "")
            + (
                f" at checkpoint {incident.checkpoint_index}"
                if incident.checkpoint_index is not None
                else ""
            )
        )
        dedupe_key = (
            f"patrol:{incident.flight_id}:{incident.incident_type}:{zone_part}:{track_part}"
        )

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
    ) -> OperationalAlert | None:
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
