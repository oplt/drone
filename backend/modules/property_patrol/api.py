from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import require_user
from backend.modules.property_patrol.models import (
    PropertyPatrolIncident,
    PropertyPatrolRun,
    PropertyPatrolSensorEvent,
    PropertyPatrolSite,
    PropertyPatrolTemplate,
)
from backend.modules.property_patrol.schemas import (
    IncidentCreate,
    IncidentOut,
    IncidentUpdate,
    MissionRunOut,
    MissionStartIn,
    MissionValidateIn,
    PatrolTemplateCreate,
    PatrolTemplateOut,
    PatrolTemplateUpdate,
    PropertyPatrolSiteCreate,
    PropertyPatrolSiteOut,
    PropertyPatrolSiteUpdate,
    RoutePreviewIn,
    RoutePreviewOut,
    SensorEventCreate,
    SensorEventOut,
    SensorEventResponse,
    ValidationResult,
)
from backend.modules.property_patrol.services.dispatch import dispatch_service
from backend.modules.property_patrol.services.geometry import polygon_from_geojson
from backend.modules.property_patrol.services.policy import policy_engine
from backend.modules.property_patrol.services.route_planner import route_planner
from backend.modules.property_patrol.services.sensor_events import sensor_event_to_raw_payload, sensor_event_validator
from backend.modules.property_patrol.services.state_machine import state_machine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/property-patrol", tags=["property-patrol"])


def _owner_filter(model: Any, user: Any) -> list[Any]:
    org_id = getattr(user, "org_id", None)
    filters = []
    if hasattr(model, "owner_id"):
        filters.append(model.owner_id == getattr(user, "id", None))
    if org_id is not None and hasattr(model, "org_id"):
        filters.append(model.org_id == org_id)
    return filters


async def _get_site(db: AsyncSession, site_id: int, user: Any) -> PropertyPatrolSite:
    stmt = select(PropertyPatrolSite).where(PropertyPatrolSite.id == site_id)
    site = await db.scalar(stmt)
    if site is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission site not found")
    return site


async def _get_template(db: AsyncSession, template_id: int) -> PropertyPatrolTemplate:
    template = await db.scalar(select(PropertyPatrolTemplate).where(PropertyPatrolTemplate.id == template_id))
    if template is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission template not found")
    return template


def _validate_site_payload(payload: PropertyPatrolSiteCreate | PropertyPatrolSiteUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    for key in ("property_boundary", "flight_safe_area"):
        if data.get(key) is not None:
            polygon_from_geojson(data[key], name=key)
    for key in ("no_fly_zones", "privacy_zones", "emergency_landing_zones"):
        for idx, poly in enumerate(data.get(key) or []):
            polygon_from_geojson(poly, name=f"{key}[{idx}]")


def _template_from_preview(site: PropertyPatrolSite, payload: RoutePreviewIn) -> PropertyPatrolTemplate:
    return PropertyPatrolTemplate(
        site_id=site.id,
        name="route-preview",
        patrol_mode=payload.patrol_mode or "perimeter",
        altitude_m=payload.altitude_m or site.default_altitude_m,
        speed_mps=payload.speed_mps or 6.0,
        boundary_offset_m=payload.boundary_offset_m if payload.boundary_offset_m is not None else 15.0,
        grid_spacing_m=payload.grid_spacing_m or 40.0,
        overlap_percent=payload.overlap_percent if payload.overlap_percent is not None else 50.0,
        camera_direction=payload.camera_direction or "inward",
        camera_gimbal_pitch_deg=payload.camera_gimbal_pitch_deg if payload.camera_gimbal_pitch_deg is not None else 35.0,
    )


async def _resolve_template_for_preview(db: AsyncSession, site: PropertyPatrolSite, payload: RoutePreviewIn) -> PropertyPatrolTemplate:
    if payload.template_id is not None:
        template = await _get_template(db, payload.template_id)
        if template.site_id != site.id:
            raise HTTPException(status_code=400, detail="Template does not belong to the selected Property Patrol Mission site")
        return template
    return _template_from_preview(site, payload)


@router.get("/sites", response_model=list[PropertyPatrolSiteOut])
async def list_sites(user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(PropertyPatrolSite).order_by(PropertyPatrolSite.updated_at.desc()))).all()
    return [PropertyPatrolSiteOut.model_validate(row) for row in rows]


@router.post("/sites", response_model=PropertyPatrolSiteOut)
async def create_site(payload: PropertyPatrolSiteCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    _validate_site_payload(payload)
    site = PropertyPatrolSite(
        owner_id=getattr(user, "id", None),
        org_id=getattr(user, "org_id", None),
        **payload.model_dump(mode="json"),
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    logger.info("property_patrol_site_created", extra={"site_id": site.id})
    return site


@router.get("/sites/{site_id}", response_model=PropertyPatrolSiteOut)
async def get_site(site_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _get_site(db, site_id, user)


@router.patch("/sites/{site_id}", response_model=PropertyPatrolSiteOut)
async def update_site(site_id: int, payload: PropertyPatrolSiteUpdate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    _validate_site_payload(payload)
    site = await _get_site(db, site_id, user)
    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(site, key, value)
    await db.commit()
    await db.refresh(site)
    return site


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    site = await _get_site(db, site_id, user)
    await db.delete(site)
    await db.commit()


@router.get("/templates", response_model=list[PatrolTemplateOut])
async def list_templates(site_id: int | None = Query(default=None), user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    stmt = select(PropertyPatrolTemplate).order_by(PropertyPatrolTemplate.updated_at.desc())
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolTemplate.site_id == site_id)
    return list((await db.scalars(stmt)).all())


@router.post("/templates", response_model=PatrolTemplateOut)
async def create_template(payload: PatrolTemplateCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    await _get_site(db, payload.site_id, user)
    template = PropertyPatrolTemplate(**payload.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/templates/{template_id}", response_model=PatrolTemplateOut)
async def get_template(template_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _get_template(db, template_id)


@router.patch("/templates/{template_id}", response_model=PatrolTemplateOut)
async def update_template(template_id: int, payload: PatrolTemplateUpdate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    template = await _get_template(db, template_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    template = await _get_template(db, template_id)
    await db.delete(template)
    await db.commit()


@router.post("/route-preview", response_model=RoutePreviewOut)
async def route_preview(payload: RoutePreviewIn, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    site = await _get_site(db, payload.site_id, user)
    template = await _resolve_template_for_preview(db, site, payload)
    waypoints, stats = route_planner.generate(site=site, template=template)
    validation = policy_engine.validate_route(site=site, template=template, waypoints=waypoints)
    logger.info("property_patrol_route_generated", extra={"site_id": site.id, "waypoints": len(waypoints), "ok": validation.ok})
    return RoutePreviewOut(waypoints=waypoints, stats=stats, validation=validation)


@router.post("/missions/validate", response_model=RoutePreviewOut)
async def validate_mission(payload: MissionValidateIn, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    site = await _get_site(db, payload.site_id, user)
    template = await _resolve_template_for_preview(db, site, payload)
    waypoints = [wp.model_dump() for wp in payload.route_waypoints] if payload.route_waypoints else route_planner.generate(site=site, template=template)[0]
    validation = policy_engine.validate_route(site=site, template=template, waypoints=waypoints)
    return RoutePreviewOut(waypoints=waypoints, stats={"waypoints": len(waypoints)}, validation=validation)


@router.post("/missions/start", response_model=MissionRunOut)
async def start_mission(payload: MissionStartIn, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    site = await _get_site(db, payload.site_id, user)
    template = await _resolve_template_for_preview(db, site, payload)
    waypoints, _stats = route_planner.generate(site=site, template=template)
    run, validation = await dispatch_service.create_validated_run(
        db=db,
        site=site,
        template=template,
        route_waypoints=waypoints,
        mission_type=payload.mission_type,
        operator_id=getattr(user, "id", None),
        drone_id=payload.drone_id,
    )
    if not validation.ok:
        await db.commit()
        raise HTTPException(status_code=422, detail=[err.model_dump() for err in validation.errors])
    await dispatch_service.dispatch_after_preflight(db=db, run=run)
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/missions", response_model=list[MissionRunOut])
async def list_missions(site_id: int | None = None, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    stmt = select(PropertyPatrolRun).order_by(PropertyPatrolRun.updated_at.desc())
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolRun.site_id == site_id)
    return list((await db.scalars(stmt)).all())


@router.get("/missions/{mission_run_id}", response_model=MissionRunOut)
async def get_mission(mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    run = await db.get(PropertyPatrolRun, mission_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission run not found")
    return run


async def _mission_command(mission_run_id: int, command: str, db: AsyncSession) -> PropertyPatrolRun:
    run = await db.get(PropertyPatrolRun, mission_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission run not found")
    try:
        dispatch_service.operator_transition(run, command)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/missions/{mission_run_id}/approve", response_model=MissionRunOut)
async def approve_mission(mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    run = await db.get(PropertyPatrolRun, mission_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission run not found")
    preflight = await dispatch_service.dispatch_after_preflight(db=db, run=run)
    if not preflight.ok:
        await db.commit()
        raise HTTPException(status_code=422, detail=[err.model_dump() for err in preflight.errors])
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/missions/{mission_run_id}/pause", response_model=MissionRunOut)
async def pause_mission(mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _mission_command(mission_run_id, "pause", db)


@router.post("/missions/{mission_run_id}/resume", response_model=MissionRunOut)
async def resume_mission(mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _mission_command(mission_run_id, "resume", db)


@router.post("/missions/{mission_run_id}/abort", response_model=MissionRunOut)
async def abort_mission(mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _mission_command(mission_run_id, "abort", db)


@router.post("/missions/{mission_run_id}/return-home", response_model=MissionRunOut)
async def return_home_mission(mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _mission_command(mission_run_id, "return-home", db)


@router.post("/sensor-events", response_model=SensorEventResponse)
async def create_sensor_event(payload: SensorEventCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    if payload.site_id is None:
        raise HTTPException(status_code=400, detail="site_id is required; sensor coordinates cannot select a site implicitly")
    site = await _get_site(db, payload.site_id, user)
    validation = await sensor_event_validator.validate(db=db, site=site, payload=payload)
    status = "validated" if validation.ok else ("duplicate" if any(e.code == "duplicate_event" for e in validation.errors) else "rejected")
    if status == "duplicate":
        existing = await db.scalar(
            select(PropertyPatrolSensorEvent).where(
                PropertyPatrolSensorEvent.site_id == site.id,
                PropertyPatrolSensorEvent.external_event_id == payload.external_event_id,
            )
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
        timestamp=payload.timestamp.astimezone(UTC) if payload.timestamp.tzinfo else payload.timestamp.replace(tzinfo=UTC),
        approx_location=payload.approx_location.model_dump() if payload.approx_location else None,
        evidence_clip_id=payload.evidence_clip_id,
        raw_payload=sensor_event_to_raw_payload(payload),
        signature_valid=bool(payload.signature),
        status=status,
        rejection_reason=None if validation.ok else "; ".join(err.message for err in validation.errors),
    )
    db.add(event)
    await db.flush()
    logger.info("property_patrol_sensor_event_received", extra={"event_id": event.id, "status": status})

    if not validation.ok:
        await db.commit()
        await db.refresh(event)
        return SensorEventResponse(event=SensorEventOut.model_validate(event), action="duplicate" if status == "duplicate" else "rejected", validation=validation)

    template = await db.scalar(select(PropertyPatrolTemplate).where(PropertyPatrolTemplate.site_id == site.id).order_by(PropertyPatrolTemplate.updated_at.desc()))
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
    return SensorEventResponse(
        event=SensorEventOut.model_validate(event),
        action=action,  # type: ignore[arg-type]
        mission_run=MissionRunOut.model_validate(run) if run is not None else None,
        incident_id=incident.id,
        validation=validation,
    )


@router.get("/sensor-events", response_model=list[SensorEventOut])
async def list_sensor_events(site_id: int | None = None, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    stmt = select(PropertyPatrolSensorEvent).order_by(PropertyPatrolSensorEvent.created_at.desc())
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolSensorEvent.site_id == site_id)
    return list((await db.scalars(stmt)).all())


@router.get("/incidents", response_model=list[IncidentOut])
async def list_incidents(site_id: int | None = None, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    stmt = select(PropertyPatrolIncident).order_by(PropertyPatrolIncident.updated_at.desc())
    if site_id is not None:
        stmt = stmt.where(PropertyPatrolIncident.site_id == site_id)
    return list((await db.scalars(stmt)).all())


@router.post("/incidents", response_model=IncidentOut)
async def create_incident(payload: IncidentCreate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    incident = PropertyPatrolIncident(**payload.model_dump(mode="json"))
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    logger.info("property_patrol_incident_created", extra={"incident_id": incident.id})
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    incident = await db.get(PropertyPatrolIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission incident not found")
    return incident


@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
async def update_incident(incident_id: int, payload: IncidentUpdate, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    incident = await db.get(PropertyPatrolIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission incident not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(incident, key, value)
    await db.commit()
    await db.refresh(incident)
    return incident


async def _incident_status(incident_id: int, status: str, db: AsyncSession) -> PropertyPatrolIncident:
    incident = await db.get(PropertyPatrolIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Property Patrol Mission incident not found")
    incident.status = status
    await db.commit()
    await db.refresh(incident)
    logger.info("property_patrol_incident_status_changed", extra={"incident_id": incident.id, "status": status})
    return incident


@router.post("/incidents/{incident_id}/acknowledge", response_model=IncidentOut)
async def acknowledge_incident(incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _incident_status(incident_id, "acknowledged", db)


@router.post("/incidents/{incident_id}/mark-false-positive", response_model=IncidentOut)
async def false_positive_incident(incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _incident_status(incident_id, "false_positive", db)


@router.post("/incidents/{incident_id}/close", response_model=IncidentOut)
async def close_incident(incident_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await _incident_status(incident_id, "closed", db)
