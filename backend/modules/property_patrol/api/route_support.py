from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.modules.property_patrol import repository as property_patrol_repository
from backend.modules.property_patrol.models import PropertyPatrolIncident, PropertyPatrolRun, PropertyPatrolSite, PropertyPatrolTemplate
from backend.modules.property_patrol.schemas import (
    PropertyPatrolSiteCreate,
    PropertyPatrolSiteUpdate,
    RoutePreviewIn,
)
from backend.modules.property_patrol.services.geometry import polygon_from_geojson


async def get_site(db: Any, site_id: int, user: Any) -> PropertyPatrolSite:
    return await property_patrol_repository.get_site(db, site_id)


async def get_template(db: Any, template_id: int) -> PropertyPatrolTemplate:
    return await property_patrol_repository.get_template(db, template_id)


def validate_site_payload(payload: PropertyPatrolSiteCreate | PropertyPatrolSiteUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    for key in ("property_boundary", "flight_safe_area"):
        if data.get(key) is not None:
            polygon_from_geojson(data[key], name=key)
    for key in ("no_fly_zones", "privacy_zones", "emergency_landing_zones"):
        for idx, poly in enumerate(data.get(key) or []):
            polygon_from_geojson(poly, name=f"{key}[{idx}]")


def template_from_preview(site: PropertyPatrolSite, payload: RoutePreviewIn) -> PropertyPatrolTemplate:
    return PropertyPatrolTemplate(
        site_id=site.id,
        name="route-preview",
        patrol_mode=payload.patrol_mode or "perimeter",
        altitude_m=payload.altitude_m or site.default_altitude_m,
        speed_mps=payload.speed_mps or 6.0,
        boundary_offset_m=payload.boundary_offset_m
        if payload.boundary_offset_m is not None
        else 15.0,
        grid_spacing_m=payload.grid_spacing_m or 40.0,
        overlap_percent=payload.overlap_percent if payload.overlap_percent is not None else 50.0,
        camera_direction=payload.camera_direction or "inward",
        camera_gimbal_pitch_deg=payload.camera_gimbal_pitch_deg
        if payload.camera_gimbal_pitch_deg is not None
        else 35.0,
    )


async def resolve_template_for_preview(
    db: Any, site: PropertyPatrolSite, payload: RoutePreviewIn
) -> PropertyPatrolTemplate:
    if payload.template_id is not None:
        template = await get_template(db, payload.template_id)
        if template.site_id != site.id:
            raise HTTPException(
                status_code=400,
                detail="Template does not belong to the selected Property Patrol Mission site",
            )
        return template
    return template_from_preview(site, payload)


async def mission_command(
    mission_run_id: int, command: str, db: Any
) -> PropertyPatrolRun:
    from backend.modules.property_patrol.services.dispatch import dispatch_service

    run = await property_patrol_repository.get_run(db, mission_run_id)
    try:
        dispatch_service.operator_transition(run, command)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(run)
    return run


async def incident_status(
    incident_id: int, status: str, db: Any
) -> PropertyPatrolIncident:
    import logging

    logger = logging.getLogger(__name__)
    incident = await property_patrol_repository.get_incident(db, incident_id)
    incident.status = status
    await db.commit()
    await db.refresh(incident)
    logger.info(
        "property_patrol_incident_status_changed",
        extra={"incident_id": incident.id, "status": status},
    )
    return incident
