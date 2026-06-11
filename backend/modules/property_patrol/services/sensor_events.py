from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.property_patrol.models import (
    PropertyPatrolSensorEvent,
    PropertyPatrolSite,
)
from backend.modules.property_patrol.schemas import (
    SensorEventCreate,
    ValidationIssue,
    ValidationResult,
)
from backend.modules.property_patrol.services.policy import policy_engine


class PatrolSensorEventValidator:
    min_confidence = 0.55
    max_age = timedelta(minutes=10)
    future_skew = timedelta(minutes=2)

    async def validate(
        self,
        *,
        db: AsyncSession,
        site: PropertyPatrolSite,
        payload: SensorEventCreate,
    ) -> ValidationResult:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        duplicate = await db.scalar(
            select(PropertyPatrolSensorEvent).where(
                PropertyPatrolSensorEvent.site_id == site.id,
                PropertyPatrolSensorEvent.external_event_id == payload.external_event_id,
            )
        )
        if duplicate is not None:
            errors.append(ValidationIssue(code="duplicate_event", message="Duplicate external_event_id for this site."))

        now = datetime.now(UTC)
        ts = payload.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts < now - self.max_age:
            errors.append(ValidationIssue(code="event_too_old", message="Sensor event timestamp is too old."))
        if ts > now + self.future_skew:
            errors.append(ValidationIssue(code="event_from_future", message="Sensor event timestamp is too far in the future."))
        if payload.confidence < self.min_confidence:
            errors.append(ValidationIssue(code="low_confidence", message="Sensor event confidence below dispatch threshold."))
        if not payload.sensor_id.strip():
            errors.append(ValidationIssue(code="unknown_sensor", message="sensor_id is required."))

        loc = payload.approx_location.model_dump() if payload.approx_location else None
        loc_validation = policy_engine.validate_sensor_location(site=site, approx_location=loc)
        errors.extend(loc_validation.errors)
        warnings.extend(loc_validation.warnings)
        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


sensor_event_validator = PatrolSensorEventValidator()


def sensor_event_to_raw_payload(payload: SensorEventCreate) -> dict[str, Any]:
    body = payload.model_dump(mode="json")
    signature = body.pop("signature", None)
    body["signature_present"] = bool(signature)
    return body

