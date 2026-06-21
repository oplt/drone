from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.modules.fields.models import Field
from backend.modules.identity.models import User
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.config_models import PatrolEventTriggerConfig
from backend.modules.patrol.geo import normalize_polygon_lonlat
from backend.modules.patrol.sensor_config_schemas import (
    PatrolEventTriggerConfigIn,
    PatrolEventTriggerConfigOut,
    PatrolMqttIntegrationOut,
    PatrolSensorIntegrationOut,
    PatrolSensorTriggerIn,
)
from backend.modules.patrol.sensor_config_service import get_accessible_field, validate_geofence_polygon


@dataclass(frozen=True)
class ResolvedEventTriggerContext:
    config: PatrolEventTriggerConfig
    field: Field
    effective_payload: PatrolSensorTriggerIn


def _org_filters(*, org_id: int | None, owner_id: int) -> list[Any]:
    filters: list[Any] = []
    if org_id is not None:
        filters.append(PatrolEventTriggerConfig.org_id == org_id)
    else:
        filters.append(PatrolEventTriggerConfig.owner_id == owner_id)
    return filters


def config_to_out(config: PatrolEventTriggerConfig) -> PatrolEventTriggerConfigOut:
    field_name = config.field.name if config.field is not None else None
    return PatrolEventTriggerConfigOut(
        id=config.id,
        field_id=config.field_id,
        field_name=field_name,
        is_active=config.is_active,
        enabled=config.enabled,
        cruise_alt=float(config.cruise_alt),
        speed_mps=float(config.speed_mps),
        verification_loiter_s=float(config.verification_loiter_s),
        verification_radius_m=float(config.verification_radius_m),
        track_target=bool(config.track_target),
        target_label=config.target_label,
        search_grid_spacing_m=float(config.search_grid_spacing_m),
        search_grid_angle_deg=float(config.search_grid_angle_deg),
        ai_tasks=list(config.ai_tasks or PATROL_AI_TASKS),
    )


async def get_event_trigger_config(
    db: AsyncSession,
    *,
    field_id: int,
    org_id: int | None,
    owner_id: int,
) -> PatrolEventTriggerConfig | None:
    stmt = (
        select(PatrolEventTriggerConfig)
        .options(selectinload(PatrolEventTriggerConfig.field))
        .where(
            PatrolEventTriggerConfig.field_id == field_id,
            *_org_filters(org_id=org_id, owner_id=owner_id),
        )
        .limit(1)
    )
    return await db.scalar(stmt)


async def get_active_event_trigger_config(
    db: AsyncSession,
    *,
    org_id: int | None,
    owner_id: int,
) -> PatrolEventTriggerConfig | None:
    stmt = (
        select(PatrolEventTriggerConfig)
        .options(selectinload(PatrolEventTriggerConfig.field))
        .where(
            PatrolEventTriggerConfig.is_active.is_(True),
            PatrolEventTriggerConfig.enabled.is_(True),
            *_org_filters(org_id=org_id, owner_id=owner_id),
        )
        .order_by(PatrolEventTriggerConfig.updated_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)


async def clear_active_event_trigger_configs(
    db: AsyncSession,
    *,
    org_id: int | None,
    owner_id: int,
    except_config_id: int | None = None,
) -> None:
    stmt = (
        update(PatrolEventTriggerConfig)
        .where(*_org_filters(org_id=org_id, owner_id=owner_id))
        .values(is_active=False)
    )
    if except_config_id is not None:
        stmt = stmt.where(PatrolEventTriggerConfig.id != except_config_id)
    await db.execute(stmt)


async def upsert_event_trigger_config(
    db: AsyncSession,
    payload: PatrolEventTriggerConfigIn,
    *,
    user: User,
    org_id: int | None,
    set_active: bool = True,
) -> PatrolEventTriggerConfig:
    field = await get_accessible_field(db, field_id=payload.field_id, user=user)
    owner_id = int(user.id)
    existing = await get_event_trigger_config(
        db,
        field_id=payload.field_id,
        org_id=org_id,
        owner_id=owner_id,
    )
    if set_active:
        await clear_active_event_trigger_configs(
            db,
            org_id=org_id,
            owner_id=owner_id,
            except_config_id=existing.id if existing is not None else None,
        )

    data = payload.model_dump(exclude={"field_id"})
    if existing is None:
        config = PatrolEventTriggerConfig(
            owner_id=owner_id,
            org_id=org_id,
            field_id=payload.field_id,
            is_active=set_active,
            **data,
        )
        db.add(config)
    else:
        config = existing
        for key, value in data.items():
            setattr(config, key, value)
        if set_active:
            config.is_active = True
    await db.commit()
    await db.refresh(config)
    config.field = field
    return config


async def field_geofence_lonlat(db: AsyncSession, field: Field) -> tuple[tuple[float, float], ...]:
    if field.boundary is None:
        raise HTTPException(
            status_code=422,
            detail="Property geofence boundary is missing.",
        )
    poly = to_shape(field.boundary)
    ring = [[float(lon), float(lat)] for lon, lat in poly.exterior.coords]
    return validate_geofence_polygon(ring)


def _config_payload_fields(config: PatrolEventTriggerConfig) -> dict[str, Any]:
    return {
        "cruise_alt": float(config.cruise_alt),
        "speed_mps": float(config.speed_mps),
        "verification_loiter_s": float(config.verification_loiter_s),
        "verification_radius_m": float(config.verification_radius_m),
        "track_target": bool(config.track_target),
        "target_label": config.target_label,
        "search_grid_spacing_m": float(config.search_grid_spacing_m),
        "search_grid_angle_deg": float(config.search_grid_angle_deg),
        "ai_tasks": list(config.ai_tasks or PATROL_AI_TASKS),
    }


async def resolve_event_trigger_payload(
    db: AsyncSession,
    payload: PatrolSensorTriggerIn,
    *,
    org_id: int | None,
    owner_id: int,
) -> ResolvedEventTriggerContext | None:
    config: PatrolEventTriggerConfig | None = None
    if payload.field_id is not None:
        config = await get_event_trigger_config(
            db,
            field_id=int(payload.field_id),
            org_id=org_id,
            owner_id=owner_id,
        )
        if config is not None and not config.enabled:
            raise HTTPException(
                status_code=422,
                detail="Event trigger setup for this property geofence is disabled.",
            )
    if config is None:
        config = await get_active_event_trigger_config(db, org_id=org_id, owner_id=owner_id)
    if config is None:
        return None

    field = config.field
    if field is None:
        field = await db.get(Field, config.field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Property geofence not found.")

    geofence_tuple = await field_geofence_lonlat(db, field)
    geofence = [list(pt) for pt in geofence_tuple]
    fields = _config_payload_fields(config)
    sensor_id = (payload.sensor_id or "webhook").strip() or "webhook"
    effective = PatrolSensorTriggerIn(
        trigger_id=payload.trigger_id,
        sensor_id=sensor_id,
        field_id=config.field_id,
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
    return ResolvedEventTriggerContext(
        config=config,
        field=field,
        effective_payload=effective,
    )


def patrol_mqtt_topic(*, org_id: int | None, owner_id: int) -> str:
    if org_id is not None:
        return f"patrol/event-triggers/org/{org_id}"
    return f"patrol/event-triggers/user/{owner_id}"


def patrol_mqtt_subscribe_pattern() -> str:
    return "patrol/event-triggers/#"


def build_event_trigger_integration_info(
    *,
    base_url: str,
    org_id: int | None,
    owner_id: int,
    mqtt_broker: str | None = None,
    mqtt_port: int | None = None,
    mqtt_use_tls: bool | None = None,
) -> PatrolSensorIntegrationOut:
    from backend.core.config.runtime import settings

    broker = mqtt_broker if mqtt_broker is not None else settings.mqtt_broker
    port = int(mqtt_port if mqtt_port is not None else settings.mqtt_port)
    use_tls = bool(mqtt_use_tls if mqtt_use_tls is not None else settings.mqtt_use_tls)
    mqtt_topic = patrol_mqtt_topic(org_id=org_id, owner_id=owner_id)
    webhook_url = f"{base_url.rstrip('/')}/api/patrol/sensor-triggers"
    example_body = {
        "trigger_id": "evt-20260622-001",
        "sensor_id": "gate-camera-east",
        "coordinates": [-122.4194, 37.7749],
    }
    return PatrolSensorIntegrationOut(
        webhook_url=webhook_url,
        auth_hint="Authorization: Bearer sk-<prefix>_<secret>  (create under Settings → Credentials → API keys)",
        example_body=example_body,
        mqtt=PatrolMqttIntegrationOut(
            broker=broker,
            port=port,
            use_tls=use_tls,
            topic=mqtt_topic,
            subscribe_pattern=patrol_mqtt_subscribe_pattern(),
            auth_hint=(
                "Publish JSON to the topic using your MQTT broker credentials. "
                "Configure the broker under Settings → Telemetry → MQTT Broker."
            ),
            qos=1,
        ),
    )


def normalize_field_polygon(field: Field) -> list[list[float]] | None:
    if field.boundary is None:
        return None
    poly = to_shape(field.boundary)
    ring = [[float(lon), float(lat)] for lon, lat in poly.exterior.coords]
    normalized = normalize_polygon_lonlat(ring)
    if len(normalized) < 3:
        return None
    return [list(pt) for pt in normalized]
