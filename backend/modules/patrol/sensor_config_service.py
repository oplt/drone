from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.modules.fields.models import Field
from backend.modules.fields.service import field_service
from backend.modules.identity.models import User
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.config_models import (
    PatrolResponseProfile,
    PatrolSensor,
    PatrolSite,
    PatrolTriggerReceipt,
)
from backend.modules.patrol.geo import normalize_polygon_lonlat
from backend.modules.patrol.sensor_config_schemas import (
    PatrolSensorIntegrationOut,
    PatrolSensorTriggerIn,
    PatrolSiteOut,
)


@dataclass(frozen=True)
class ResolvedPatrolSensorContext:
    sensor: PatrolSensor
    site: PatrolSite
    profile: PatrolResponseProfile
    effective_payload: PatrolSensorTriggerIn


def _org_filters(model: Any, *, org_id: int | None, owner_id: int) -> list[Any]:
    filters: list[Any] = []
    if org_id is not None and hasattr(model, "org_id"):
        filters.append(model.org_id == org_id)
    elif hasattr(model, "owner_id"):
        filters.append(model.owner_id == owner_id)
    return filters


async def get_site(db: AsyncSession, *, site_id: int, org_id: int | None, owner_id: int) -> PatrolSite:
    stmt = select(PatrolSite).where(PatrolSite.id == site_id, *_org_filters(PatrolSite, org_id=org_id, owner_id=owner_id))
    site = await db.scalar(stmt)
    if site is None:
        raise HTTPException(status_code=404, detail="Patrol site not found")
    return site


async def list_sites(db: AsyncSession, *, org_id: int | None, owner_id: int) -> list[PatrolSite]:
    stmt = (
        select(PatrolSite)
        .options(selectinload(PatrolSite.field))
        .where(*_org_filters(PatrolSite, org_id=org_id, owner_id=owner_id))
        .order_by(PatrolSite.name.asc())
    )
    return list((await db.scalars(stmt)).all())


async def get_accessible_field(
    db: AsyncSession,
    *,
    field_id: int,
    user: User,
) -> Field:
    field = await field_service.get_owned(db, field_id=field_id, user=user)
    if field is None:
        raise HTTPException(status_code=404, detail="Property geofence not found.")
    return field


def site_to_out(site: PatrolSite) -> PatrolSiteOut:
    field_name = site.field.name if site.field is not None else None
    return PatrolSiteOut(
        id=site.id,
        field_id=site.field_id,
        field_name=field_name,
        name=site.name,
        description=site.description,
        enabled=site.enabled,
    )


async def resolve_site_geofence_lonlat(
    db: AsyncSession,
    site: PatrolSite,
) -> tuple[tuple[float, float], ...]:
    field = await db.get(Field, site.field_id)
    if field is None or field.boundary is None:
        raise HTTPException(
            status_code=422,
            detail="Patrol site property geofence boundary is missing.",
        )
    poly = to_shape(field.boundary)
    ring = [[float(lon), float(lat)] for lon, lat in poly.exterior.coords]
    return validate_geofence_polygon(ring)


async def get_profile_for_site(
    db: AsyncSession,
    *,
    site_id: int,
    profile_id: int | None,
    org_id: int | None,
    owner_id: int,
) -> PatrolResponseProfile:
    await get_site(db, site_id=site_id, org_id=org_id, owner_id=owner_id)
    if profile_id is not None:
        profile = await db.scalar(
            select(PatrolResponseProfile).where(
                PatrolResponseProfile.id == profile_id,
                PatrolResponseProfile.site_id == site_id,
            )
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="Response profile not found for this site")
        return profile

    profile = await db.scalar(
        select(PatrolResponseProfile)
        .where(
            PatrolResponseProfile.site_id == site_id,
            PatrolResponseProfile.enabled.is_(True),
            PatrolResponseProfile.is_default.is_(True),
        )
        .limit(1)
    )
    if profile is not None:
        return profile

    profile = await db.scalar(
        select(PatrolResponseProfile)
        .where(PatrolResponseProfile.site_id == site_id, PatrolResponseProfile.enabled.is_(True))
        .order_by(PatrolResponseProfile.id.asc())
        .limit(1)
    )
    if profile is None:
        raise HTTPException(
            status_code=422,
            detail="Site has no enabled response profile. Create one before registering sensors.",
        )
    return profile


async def list_profiles(
    db: AsyncSession,
    *,
    site_id: int | None,
    org_id: int | None,
    owner_id: int,
) -> list[PatrolResponseProfile]:
    stmt = select(PatrolResponseProfile).join(PatrolSite, PatrolSite.id == PatrolResponseProfile.site_id)
    filters = _org_filters(PatrolSite, org_id=org_id, owner_id=owner_id)
    if site_id is not None:
        filters.append(PatrolResponseProfile.site_id == site_id)
    stmt = stmt.where(*filters).order_by(PatrolResponseProfile.site_id.asc(), PatrolResponseProfile.name.asc())
    return list((await db.scalars(stmt)).all())


async def list_sensors(
    db: AsyncSession,
    *,
    site_id: int | None,
    org_id: int | None,
    owner_id: int,
) -> list[PatrolSensor]:
    stmt = select(PatrolSensor).options(selectinload(PatrolSensor.site))
    filters = _org_filters(PatrolSensor, org_id=org_id, owner_id=owner_id)
    if site_id is not None:
        filters.append(PatrolSensor.site_id == site_id)
    stmt = stmt.where(*filters).order_by(PatrolSensor.name.asc())
    return list((await db.scalars(stmt)).all())


async def get_sensor_by_external_id(
    db: AsyncSession,
    *,
    external_sensor_id: str,
    org_id: int | None,
    owner_id: int,
) -> PatrolSensor | None:
    stmt = (
        select(PatrolSensor)
        .options(selectinload(PatrolSensor.site), selectinload(PatrolSensor.response_profile))
        .where(
            PatrolSensor.external_sensor_id == str(external_sensor_id).strip(),
            *_org_filters(PatrolSensor, org_id=org_id, owner_id=owner_id),
        )
        .limit(1)
    )
    return await db.scalar(stmt)


async def get_sensor(db: AsyncSession, *, sensor_pk: int, org_id: int | None, owner_id: int) -> PatrolSensor:
    stmt = (
        select(PatrolSensor)
        .options(selectinload(PatrolSensor.site), selectinload(PatrolSensor.response_profile))
        .where(PatrolSensor.id == sensor_pk, *_org_filters(PatrolSensor, org_id=org_id, owner_id=owner_id))
    )
    sensor = await db.scalar(stmt)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Patrol sensor not found")
    return sensor


async def clear_default_profiles(db: AsyncSession, *, site_id: int, except_profile_id: int | None = None) -> None:
    stmt = update(PatrolResponseProfile).where(PatrolResponseProfile.site_id == site_id).values(is_default=False)
    if except_profile_id is not None:
        stmt = stmt.where(PatrolResponseProfile.id != except_profile_id)
    await db.execute(stmt)


def build_integration_info(*, base_url: str, external_sensor_id: str) -> PatrolSensorIntegrationOut:
    webhook_url = f"{base_url.rstrip('/')}/api/patrol/sensor-triggers"
    return PatrolSensorIntegrationOut(
        webhook_url=webhook_url,
        auth_hint="Authorization: Bearer sk-<prefix>_<secret>  (create under Settings → Credentials → API keys)",
        example_body={
            "trigger_id": "evt-20260620-001",
            "sensor_id": external_sensor_id,
            "coordinates": [-122.4194, 37.7749],
        },
    )


def _profile_payload_fields(profile: PatrolResponseProfile) -> dict[str, Any]:
    return {
        "geofence_polygon_lonlat": None,
        "cruise_alt": float(profile.cruise_alt),
        "speed_mps": float(profile.speed_mps),
        "verification_loiter_s": float(profile.verification_loiter_s),
        "verification_radius_m": float(profile.verification_radius_m),
        "track_target": bool(profile.track_target),
        "target_label": profile.target_label,
        "search_grid_spacing_m": float(profile.search_grid_spacing_m),
        "search_grid_angle_deg": float(profile.search_grid_angle_deg),
        "ai_tasks": list(profile.ai_tasks or PATROL_AI_TASKS),
    }


async def resolve_registered_sensor_trigger(
    db: AsyncSession,
    payload: PatrolSensorTriggerIn,
    *,
    org_id: int | None,
    owner_id: int,
) -> ResolvedPatrolSensorContext | None:
    if not payload.sensor_id:
        return None
    sensor = await get_sensor_by_external_id(
        db,
        external_sensor_id=payload.sensor_id,
        org_id=org_id,
        owner_id=owner_id,
    )
    if sensor is None:
        return None
    if not sensor.enabled:
        raise HTTPException(status_code=422, detail=f"Sensor '{payload.sensor_id}' is disabled.")
    if not sensor.site.enabled:
        raise HTTPException(status_code=422, detail="Patrol site for this sensor is disabled.")

    profile = sensor.response_profile
    if profile is None or not profile.enabled:
        profile = await get_profile_for_site(
            db,
            site_id=sensor.site_id,
            profile_id=None,
            org_id=org_id,
            owner_id=owner_id,
        )
    if not profile.enabled:
        raise HTTPException(status_code=422, detail="Linked response profile is disabled.")

    geofence_tuple = await resolve_site_geofence_lonlat(db, sensor.site)
    geofence = [list(pt) for pt in geofence_tuple]
    fields = _profile_payload_fields(profile)
    effective = PatrolSensorTriggerIn(
        trigger_id=payload.trigger_id,
        sensor_id=payload.sensor_id,
        coordinates=payload.coordinates,
        mission_name=payload.mission_name,
        geofence_polygon_lonlat=geofence,
        cruise_alt=payload.cruise_alt if payload.cruise_alt is not None else fields["cruise_alt"],
        speed_mps=payload.speed_mps if payload.speed_mps is not None else fields["speed_mps"],
        verification_loiter_s=(
            payload.verification_loiter_s
            if payload.verification_loiter_s is not None
            else fields["verification_loiter_s"]
        ),
        verification_radius_m=(
            payload.verification_radius_m
            if payload.verification_radius_m is not None
            else fields["verification_radius_m"]
        ),
        track_target=payload.track_target if payload.track_target is not None else fields["track_target"],
        target_label=payload.target_label if payload.target_label is not None else fields["target_label"],
        search_grid_spacing_m=(
            payload.search_grid_spacing_m
            if payload.search_grid_spacing_m is not None
            else fields["search_grid_spacing_m"]
        ),
        search_grid_angle_deg=(
            payload.search_grid_angle_deg
            if payload.search_grid_angle_deg is not None
            else fields["search_grid_angle_deg"]
        ),
        ai_tasks=payload.ai_tasks if payload.ai_tasks is not None else fields["ai_tasks"],
    )
    return ResolvedPatrolSensorContext(
        sensor=sensor,
        site=sensor.site,
        profile=profile,
        effective_payload=effective,
    )


async def get_trigger_receipt(
    db: AsyncSession,
    *,
    org_id: int,
    trigger_id: str,
) -> PatrolTriggerReceipt | None:
    return await db.scalar(
        select(PatrolTriggerReceipt).where(
            PatrolTriggerReceipt.org_id == org_id,
            PatrolTriggerReceipt.trigger_id == str(trigger_id).strip(),
        )
    )


async def release_trigger_receipt(
    db: AsyncSession,
    *,
    org_id: int,
    trigger_id: str,
) -> None:
    receipt = await get_trigger_receipt(db, org_id=org_id, trigger_id=trigger_id)
    if receipt is None or receipt.client_flight_id:
        return
    await db.delete(receipt)
    await db.flush()


async def claim_trigger_receipt(
    db: AsyncSession,
    *,
    org_id: int,
    trigger_id: str,
    sensor_id: str,
) -> bool:
    existing = await get_trigger_receipt(db, org_id=org_id, trigger_id=trigger_id)
    if existing is not None:
        if existing.client_flight_id:
            return False
        await db.delete(existing)
        await db.flush()

    db.add(
        PatrolTriggerReceipt(
            org_id=org_id,
            trigger_id=str(trigger_id).strip(),
            sensor_id=str(sensor_id).strip(),
        )
    )
    await db.flush()
    return True


async def finalize_trigger_receipt(
    db: AsyncSession,
    *,
    org_id: int,
    trigger_id: str,
    client_flight_id: str | None,
    response_mode: str,
) -> None:
    receipt = await db.scalar(
        select(PatrolTriggerReceipt).where(
            PatrolTriggerReceipt.org_id == org_id,
            PatrolTriggerReceipt.trigger_id == str(trigger_id).strip(),
        )
    )
    if receipt is None:
        return
    receipt.client_flight_id = client_flight_id
    receipt.response_mode = response_mode
    await db.flush()


def sensor_registry_from_sensor(sensor: PatrolSensor) -> dict[str, tuple[float, float]]:
    if not sensor.location_lonlat or len(sensor.location_lonlat) < 2:
        return {}
    lon = float(sensor.location_lonlat[0])
    lat = float(sensor.location_lonlat[1])
    return {str(sensor.external_sensor_id).strip(): (lon, lat)}


def validate_geofence_polygon(polygon: list[list[float]] | None) -> tuple[tuple[float, float], ...]:
    geofence = normalize_polygon_lonlat(polygon)
    if len(geofence) < 3:
        raise HTTPException(status_code=400, detail="geofence_polygon_lonlat requires at least 3 points.")
    return geofence
