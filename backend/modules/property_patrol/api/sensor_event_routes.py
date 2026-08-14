from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.infrastructure.jobs import enqueue_task
from backend.modules.identity.dependencies import require_user
from backend.modules.property_patrol import repository as property_patrol_repository
from backend.modules.property_patrol.api.route_support import get_site
from backend.modules.property_patrol.models import PropertyPatrolIncident, PropertyPatrolSensorEvent
from backend.modules.property_patrol.schemas import (
    MissionRunOut,
    SensorEventCreate,
    SensorEventOut,
    SensorEventResponse,
)
from backend.modules.property_patrol.services.dispatch import dispatch_service
from backend.modules.property_patrol.services.route_planner import route_planner
from backend.modules.property_patrol.services.sensor_events import (
    sensor_event_to_raw_payload,
    sensor_event_validator,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["property-patrol"])
AsyncSession = Any


@router.post("/sensor-events", response_model=SensorEventResponse)
async def create_sensor_event(
    payload: SensorEventCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    if payload.site_id is None:
        raise HTTPException(
            status_code=400,
            detail="site_id is required; sensor coordinates cannot select a site implicitly",
        )
    site = await get_site(db, payload.site_id, user)
    validation = await sensor_event_validator.validate(db=db, site=site, payload=payload)
    status = (
        "validated"
        if validation.ok
        else (
            "duplicate"
            if any(error.code == "duplicate_event" for error in validation.errors)
            else "rejected"
        )
    )
    if status == "duplicate":
        existing = await property_patrol_repository.find_sensor_event(
            db, site_id=site.id, external_event_id=payload.external_event_id
        )
        if existing is not None:
            return SensorEventResponse(
                event=SensorEventOut.model_validate(existing),
                action="duplicate",
                validation=validation,
            )
    event = PropertyPatrolSensorEvent(
        external_event_id=payload.external_event_id,
        sensor_id=payload.sensor_id,
        site_id=site.id,
        zone_id=payload.zone_id,
        event_type=payload.event_type,
        confidence=payload.confidence,
        timestamp=payload.timestamp.astimezone(UTC)
        if payload.timestamp.tzinfo
        else payload.timestamp.replace(tzinfo=UTC),
        approx_location=payload.approx_location.model_dump() if payload.approx_location else None,
        evidence_clip_id=payload.evidence_clip_id,
        raw_payload=sensor_event_to_raw_payload(payload),
        signature_valid=bool(payload.signature),
        status=status,
        rejection_reason=None
        if validation.ok
        else "; ".join(error.message for error in validation.errors),
    )
    db.add(event)
    await db.flush()
    logger.info(
        "property_patrol_sensor_event_received", extra={"event_id": event.id, "status": status}
    )

    if not validation.ok:
        await db.commit()
        await db.refresh(event)
        return SensorEventResponse(
            event=SensorEventOut.model_validate(event),
            action="duplicate" if status == "duplicate" else "rejected",
            validation=validation,
        )

    template = await property_patrol_repository.latest_template(db, site_id=site.id)
    incident = PropertyPatrolIncident(
        site_id=site.id,
        sensor_event_id=event.id,
        source="sensor",
        event_type=payload.event_type,
        severity="medium" if payload.confidence < 0.8 else "high",
        confidence=payload.confidence,
        zone_id=payload.zone_id,
        start_time=event.timestamp,
        location=event.approx_location,
        video_clip_id=payload.evidence_clip_id,
        status="open",
    )
    db.add(incident)
    await db.flush()
    behavior = template.trigger_behavior if template is not None else "approval_required"
    action: str = behavior
    run = None
    if behavior in {"approval_required", "auto_dispatch"} and template is not None:
        waypoints, _stats = route_planner.generate(site=site, template=template)
        run, route_validation = await dispatch_service.create_validated_run(
            db=db,
            site=site,
            template=template,
            route_waypoints=waypoints,
            mission_type="sensor_triggered",
            operator_id=None,
        )
        incident.mission_run_id = run.id
        validation.warnings.extend(route_validation.warnings)
        validation.errors.extend(route_validation.errors)
        validation.ok = validation.ok and route_validation.ok
        if behavior == "auto_dispatch" and route_validation.ok:
            preflight = await dispatch_service.dispatch_after_preflight(db=db, run=run)
            validation.warnings.extend(preflight.warnings)
            validation.errors.extend(preflight.errors)
            validation.ok = validation.ok and preflight.ok
            action = "dispatched" if preflight.ok else "approval_required"
            event.status = "dispatched" if preflight.ok else "validated"
        else:
            action = "approval_required"
    elif behavior == "notify_only":
        action = "notify_only"
    await db.commit()
    await db.refresh(event)
    if run is not None:
        await db.refresh(run)
    try:
        enqueue_task(
            "agents.summarize_property_patrol_incident",
            incident_id=int(incident.id),
        )
    except Exception:
        logger.exception("Failed to enqueue property patrol incident summary")
    return SensorEventResponse(
        event=SensorEventOut.model_validate(event),
        action=action,  # type: ignore[arg-type]
        mission_run=MissionRunOut.model_validate(run) if run is not None else None,
        incident_id=incident.id,
        validation=validation,
    )


@router.get("/sensor-events", response_model=Page[SensorEventOut])
async def list_sensor_events(
    site_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await property_patrol_repository.list_sensor_events(
        db, site_id=site_id, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [SensorEventOut.model_validate(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )
