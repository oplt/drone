from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.config_models import PatrolResponseProfile, PatrolSensor, PatrolSite
from backend.modules.patrol.event_trigger_config_service import (
    build_event_trigger_integration_info,
    config_to_out,
    get_event_trigger_config,
    upsert_event_trigger_config,
)
from backend.modules.patrol.sensor_config_schemas import (
    PatrolEventTriggerConfigIn,
    PatrolEventTriggerConfigOut,
    PatrolResponseProfileIn,
    PatrolResponseProfileOut,
    PatrolResponseProfileUpdate,
    PatrolSensorIn,
    PatrolSensorIntegrationOut,
    PatrolSensorOut,
    PatrolSensorTriggerIn,
    PatrolSensorTriggerOut,
    PatrolSensorUpdate,
    PatrolSiteIn,
    PatrolSiteOut,
    PatrolSiteUpdate,
)
from backend.modules.patrol.sensor_config_service import (
    build_integration_info,
    clear_default_profiles,
    find_profile,
    find_sensor_duplicate,
    find_site_for_field,
    get_accessible_field,
    get_profile_for_site,
    get_sensor,
    get_site,
    list_profiles,
    list_sensors,
    list_sites,
    site_to_out,
)
from backend.modules.patrol.trigger_dispatch import dispatch_sensor_trigger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patrol", tags=["patrol-config"])
AsyncSession = Any


def _sensor_out(sensor: PatrolSensor, *, base_url: str) -> PatrolSensorOut:
    location = None
    if sensor.location_lonlat and len(sensor.location_lonlat) >= 2:
        location = [float(sensor.location_lonlat[0]), float(sensor.location_lonlat[1])]
    return PatrolSensorOut(
        id=sensor.id,
        site_id=sensor.site_id,
        response_profile_id=sensor.response_profile_id,
        external_sensor_id=sensor.external_sensor_id,
        name=sensor.name,
        sensor_type=sensor.sensor_type,
        location_lonlat=location,
        connector_type=sensor.connector_type,
        connector_config=dict(sensor.connector_config or {}),
        enabled=sensor.enabled,
        integration=build_integration_info(
            base_url=base_url,
            external_sensor_id=sensor.external_sensor_id,
        ),
    )


@router.get("/sites", response_model=list[PatrolSiteOut])
async def list_patrol_sites(
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> list[PatrolSiteOut]:
    sites = await list_sites(db, org_id=org_user.org_id, owner_id=int(org_user.user.id))
    return [site_to_out(site) for site in sites]


@router.post("/sites", response_model=PatrolSiteOut, status_code=201)
async def create_patrol_site(
    payload: PatrolSiteIn,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolSiteOut:
    field = await get_accessible_field(db, field_id=payload.field_id, user=org_user.user)
    existing = await find_site_for_field(
        db, field_id=payload.field_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This property geofence is already linked for patrol sensors.",
        )
    site_name = payload.name.strip() if payload.name else field.name
    site = PatrolSite(
        owner_id=int(org_user.user.id),
        org_id=org_user.org_id,
        name=site_name,
        description=payload.description,
        field_id=payload.field_id,
        enabled=payload.enabled,
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    site.field = field
    return site_to_out(site)


@router.patch("/sites/{site_id}", response_model=PatrolSiteOut)
async def update_patrol_site(
    site_id: int,
    payload: PatrolSiteUpdate,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolSiteOut:
    site = await get_site(
        db, site_id=site_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    data = payload.model_dump(exclude_unset=True)
    if "field_id" in data and data["field_id"] is not None:
        field = await get_accessible_field(db, field_id=data["field_id"], user=org_user.user)
        duplicate = await find_site_for_field(
            db, field_id=data["field_id"], org_id=org_user.org_id, owner_id=int(org_user.user.id)
        )
        if duplicate is not None and duplicate.id == site_id:
            duplicate = None
        if duplicate is not None:
            raise HTTPException(
                status_code=409,
                detail="This property geofence is already linked for patrol sensors.",
            )
    for key, value in data.items():
        setattr(site, key, value)
    await db.commit()
    await db.refresh(site)
    if "field_id" in data and data["field_id"] is not None:
        site.field = field
    elif site.field is None:
        site.field = await get_accessible_field(db, field_id=site.field_id, user=org_user.user)
    return site_to_out(site)


@router.delete("/sites/{site_id}", status_code=204)
async def delete_patrol_site(
    site_id: int,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    site = await get_site(
        db, site_id=site_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    await db.delete(site)
    await db.commit()


@router.get("/response-profiles", response_model=list[PatrolResponseProfileOut])
async def list_patrol_response_profiles(
    site_id: int | None = Query(default=None),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> list[PatrolResponseProfileOut]:
    profiles = await list_profiles(
        db,
        site_id=site_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    return [PatrolResponseProfileOut.model_validate(item) for item in profiles]


@router.post("/response-profiles", response_model=PatrolResponseProfileOut, status_code=201)
async def create_patrol_response_profile(
    payload: PatrolResponseProfileIn,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolResponseProfileOut:
    await get_site(
        db, site_id=payload.site_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    if payload.is_default:
        await clear_default_profiles(db, site_id=payload.site_id)
    profile = PatrolResponseProfile(
        site_id=payload.site_id,
        name=payload.name.strip(),
        cruise_alt=payload.cruise_alt,
        speed_mps=payload.speed_mps,
        verification_loiter_s=payload.verification_loiter_s,
        verification_radius_m=payload.verification_radius_m,
        track_target=payload.track_target,
        target_label=payload.target_label,
        search_grid_spacing_m=payload.search_grid_spacing_m,
        search_grid_angle_deg=payload.search_grid_angle_deg,
        ai_tasks=list(payload.ai_tasks),
        is_default=payload.is_default,
        enabled=payload.enabled,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return PatrolResponseProfileOut.model_validate(profile)


@router.patch("/response-profiles/{profile_id}", response_model=PatrolResponseProfileOut)
async def update_patrol_response_profile(
    profile_id: int,
    payload: PatrolResponseProfileUpdate,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolResponseProfileOut:
    profile = await find_profile(
        db, profile_id=profile_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_default"):
        await clear_default_profiles(db, site_id=profile.site_id, except_profile_id=profile.id)
    for key, value in data.items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return PatrolResponseProfileOut.model_validate(profile)


@router.delete("/response-profiles/{profile_id}", status_code=204)
async def delete_patrol_response_profile(
    profile_id: int,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await find_profile(
        db, profile_id=profile_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    await db.delete(profile)
    await db.commit()


@router.get("/sensors", response_model=list[PatrolSensorOut])
async def list_patrol_sensors(
    request: Request,
    site_id: int | None = Query(default=None),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> list[PatrolSensorOut]:
    sensors = await list_sensors(
        db,
        site_id=site_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    base_url = str(request.base_url).rstrip("/")
    return [_sensor_out(sensor, base_url=base_url) for sensor in sensors]


@router.post("/sensors", response_model=PatrolSensorOut, status_code=201)
async def create_patrol_sensor(
    payload: PatrolSensorIn,
    request: Request,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolSensorOut:
    await get_site(
        db, site_id=payload.site_id, org_id=org_user.org_id, owner_id=int(org_user.user.id)
    )
    if payload.response_profile_id is not None:
        await get_profile_for_site(
            db,
            site_id=payload.site_id,
            profile_id=payload.response_profile_id,
            org_id=org_user.org_id,
            owner_id=int(org_user.user.id),
        )
    duplicate = await find_sensor_duplicate(
        db,
        external_sensor_id=payload.external_sensor_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail="external_sensor_id already exists for this organisation."
        )
    sensor = PatrolSensor(
        owner_id=int(org_user.user.id),
        org_id=org_user.org_id,
        site_id=payload.site_id,
        response_profile_id=payload.response_profile_id,
        external_sensor_id=payload.external_sensor_id.strip(),
        name=payload.name.strip(),
        sensor_type=payload.sensor_type,
        location_lonlat=payload.location_lonlat,
        connector_type=payload.connector_type,
        connector_config=dict(payload.connector_config or {}),
        enabled=payload.enabled,
    )
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    return _sensor_out(sensor, base_url=str(request.base_url).rstrip("/"))


@router.patch("/sensors/{sensor_id}", response_model=PatrolSensorOut)
async def update_patrol_sensor(
    sensor_id: int,
    payload: PatrolSensorUpdate,
    request: Request,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolSensorOut:
    sensor = await get_sensor(
        db,
        sensor_pk=sensor_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    data = payload.model_dump(exclude_unset=True)
    if "site_id" in data and data["site_id"] is not None:
        await get_site(
            db, site_id=data["site_id"], org_id=org_user.org_id, owner_id=int(org_user.user.id)
        )
    if "response_profile_id" in data and data["response_profile_id"] is not None:
        await get_profile_for_site(
            db,
            site_id=data.get("site_id", sensor.site_id),
            profile_id=data["response_profile_id"],
            org_id=org_user.org_id,
            owner_id=int(org_user.user.id),
        )
    if "external_sensor_id" in data and data["external_sensor_id"] is not None:
        data["external_sensor_id"] = data["external_sensor_id"].strip()
    for key, value in data.items():
        setattr(sensor, key, value)
    await db.commit()
    await db.refresh(sensor)
    return _sensor_out(sensor, base_url=str(request.base_url).rstrip("/"))


@router.delete("/sensors/{sensor_id}", status_code=204)
async def delete_patrol_sensor(
    sensor_id: int,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    sensor = await get_sensor(
        db,
        sensor_pk=sensor_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    await db.delete(sensor)
    await db.commit()


@router.post("/sensor-triggers", response_model=PatrolSensorTriggerOut)
async def ingest_sensor_trigger(
    payload: PatrolSensorTriggerIn,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> PatrolSensorTriggerOut:
    """Receive a sensor trigger and dispatch the appropriate patrol response flight."""
    logger.info(
        "POST /sensor-triggers trigger_id=%s org_id=%s",
        payload.trigger_id,
        org_user.org_id,
    )
    return await dispatch_sensor_trigger(payload, user=org_user.user, db=db)


@router.get("/event-trigger-config", response_model=PatrolEventTriggerConfigOut)
async def get_patrol_event_trigger_config(
    request: Request,
    field_id: int = Query(..., ge=1),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> PatrolEventTriggerConfigOut:
    config = await get_event_trigger_config(
        db,
        field_id=field_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    base_url = str(request.base_url).rstrip("/")
    integration = build_event_trigger_integration_info(
        base_url=base_url,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    if config is None:
        field = await get_accessible_field(db, field_id=field_id, user=org_user.user)
        return PatrolEventTriggerConfigOut(
            id=None,
            field_id=field_id,
            field_name=field.name,
            is_active=False,
            enabled=True,
            cruise_alt=30.0,
            speed_mps=6.0,
            verification_loiter_s=45.0,
            verification_radius_m=18.0,
            track_target=True,
            target_label=None,
            search_grid_spacing_m=40.0,
            search_grid_angle_deg=0.0,
            ai_tasks=list(PATROL_AI_TASKS),
            integration=integration,
        )
    out = config_to_out(config)
    return out.model_copy(update={"integration": integration})


@router.put("/event-trigger-config", response_model=PatrolEventTriggerConfigOut)
async def save_patrol_event_trigger_config(
    payload: PatrolEventTriggerConfigIn,
    request: Request,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolEventTriggerConfigOut:
    config = await upsert_event_trigger_config(
        db,
        payload,
        user=org_user.user,
        org_id=org_user.org_id,
        set_active=True,
    )
    integration = build_event_trigger_integration_info(
        base_url=str(request.base_url).rstrip("/"),
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    out = config_to_out(config)
    return out.model_copy(update={"integration": integration})


@router.get("/event-trigger-config/integration", response_model=PatrolSensorIntegrationOut)
async def get_patrol_event_trigger_integration(
    request: Request,
    org_user: OrgUser = Depends(require_org_user),
) -> PatrolSensorIntegrationOut:
    return build_event_trigger_integration_info(
        base_url=str(request.base_url).rstrip("/"),
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )


@router.post("/sensors/{sensor_id}/test-trigger", response_model=PatrolSensorTriggerOut)
async def test_patrol_sensor_trigger(
    sensor_id: int,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
) -> PatrolSensorTriggerOut:
    sensor = await get_sensor(
        db,
        sensor_pk=sensor_id,
        org_id=org_user.org_id,
        owner_id=int(org_user.user.id),
    )
    payload = PatrolSensorTriggerIn(
        trigger_id=f"test-{uuid.uuid4().hex[:12]}",
        sensor_id=sensor.external_sensor_id,
        coordinates=(
            [float(sensor.location_lonlat[0]), float(sensor.location_lonlat[1])]
            if sensor.location_lonlat and len(sensor.location_lonlat) >= 2
            else None
        ),
        mission_name=f"Test trigger {sensor.name}",
    )
    return await dispatch_sensor_trigger(payload, user=org_user.user, db=db)
