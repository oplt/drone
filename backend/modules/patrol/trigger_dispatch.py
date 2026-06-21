from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.missions.application import mission_application
from backend.modules.missions.service.mission_builder import flight_profile_for_payload
from backend.modules.missions.launch_service import mission_launch_service
from backend.modules.missions.schemas.mission_create import MissionCreateIn
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.missions.service.mission_start import (
    ALLOW_WARN_PREFLIGHT_START,
    _ensure_drone_ready_for_preflight,
    preflight_allows_start,
)
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.geo import point_in_polygon
from backend.modules.patrol.planning import EventTriggeredPatrolMission, normalize_ai_tasks
from backend.modules.patrol.event_trigger_config_service import resolve_event_trigger_payload
from backend.modules.patrol.sensor_config_schemas import (
    PatrolResponseMode,
    PatrolSensorTriggerIn,
    PatrolSensorTriggerOut,
    SensorLocationIn,
)
from backend.modules.patrol.sensor_config_service import (
    claim_trigger_receipt,
    finalize_trigger_receipt,
    get_trigger_receipt,
    release_trigger_receipt,
    resolve_registered_sensor_trigger,
    sensor_registry_from_sensor,
    validate_geofence_polygon,
)
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.vehicle_runtime.factory import get_orchestrator

logger = logging.getLogger(__name__)

# Webhook/MQTT triggers must not block callers indefinitely while MAVLink connects.
TRIGGER_DISPATCH_READY_TIMEOUT_S = 45.0


def register_sensor_location(sensor_id: str, lon: float, lat: float) -> None:
    _ = (sensor_id, lon, lat)


def _registry_from_payload(
    entries: list[SensorLocationIn] | None,
) -> dict[str, tuple[float, float]]:
    merged: dict[str, tuple[float, float]] = {}
    for entry in entries or []:
        lon, lat = float(entry.location_lonlat[0]), float(entry.location_lonlat[1])
        merged[str(entry.sensor_id).strip()] = (lon, lat)
    return merged


def resolve_trigger_location(
    *,
    trigger_coordinates: tuple[float, float] | None,
    sensor_id: str,
    sensor_registry: dict[str, tuple[float, float]],
) -> tuple[float, float] | None:
    if trigger_coordinates is not None:
        return trigger_coordinates
    return sensor_registry.get(str(sensor_id).strip())


def choose_response_mode(
    resolved_location: tuple[float, float] | None,
) -> PatrolResponseMode:
    if resolved_location is not None:
        return "incident_response"
    return "detection_search"


def validate_location_in_geofence(
    lon: float,
    lat: float,
    geofence: tuple[tuple[float, float], ...],
) -> bool:
    return point_in_polygon(lat, lon, geofence)


async def _ensure_drone_available(orch: Any) -> None:
    active_db_row = await mission_application.get_active()
    if active_db_row is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Drone is busy with another mission "
                f"({active_db_row.client_flight_id}, state={active_db_row.state})."
            ),
        )
    active_task = getattr(orch, "_active_mission_task", None)
    if active_task is not None and not active_task.done():
        raise HTTPException(
            status_code=409,
            detail="Drone is busy with another running mission.",
        )


def build_event_triggered_mission(
    payload: PatrolSensorTriggerIn,
    *,
    response_mode: PatrolResponseMode,
    resolved_location: tuple[float, float] | None,
    geofence: tuple[tuple[float, float], ...],
) -> EventTriggeredPatrolMission:
    ai_tasks = normalize_ai_tasks(payload.ai_tasks or PATROL_AI_TASKS)
    return EventTriggeredPatrolMission(
        trigger_id=str(payload.trigger_id).strip(),
        sensor_id=str(payload.sensor_id or "webhook").strip() or "webhook",
        response_mode=response_mode,
        event_location_lonlat=resolved_location,
        geofence_polygon_lonlat=geofence,
        altitude_agl=float(payload.cruise_alt or 30.0),
        speed_mps=float(payload.speed_mps or 6.0),
        verification_loiter_s=float(payload.verification_loiter_s or 45.0),
        verification_radius_m=float(payload.verification_radius_m or 18.0),
        track_target=bool(payload.track_target if payload.track_target is not None else True),
        target_label=payload.target_label,
        search_grid_spacing_m=float(payload.search_grid_spacing_m or 40.0),
        search_grid_angle_deg=float(payload.search_grid_angle_deg or 0.0),
        ai_tasks=ai_tasks,
    )


def _mission_create_payload(
    payload: PatrolSensorTriggerIn,
    *,
    mission_name: str,
    geofence: tuple[tuple[float, float], ...],
) -> MissionCreateIn:
    geofence_list = [list(pt) for pt in geofence]
    private_patrol: dict[str, Any] = {
        "task_type": "event_triggered_patrol",
        "property_polygon_lonlat": geofence_list,
        "trigger_event_location_lonlat": (
            list(payload.coordinates) if payload.coordinates else None
        ),
        "speed_mps": float(payload.speed_mps or 6.0),
        "verification_loiter_s": float(payload.verification_loiter_s or 45.0),
        "verification_radius_m": float(payload.verification_radius_m or 18.0),
        "track_target": bool(payload.track_target if payload.track_target is not None else True),
        "auto_stream_video": True,
        "record_video_stream": True,
        "target_label": payload.target_label,
        "ai_tasks": list(payload.ai_tasks or PATROL_AI_TASKS),
        "grid_spacing_m": float(payload.search_grid_spacing_m or 40.0),
        "grid_angle_deg": float(payload.search_grid_angle_deg or 0.0),
    }
    return MissionCreateIn(
        name=mission_name,
        cruise_alt=float(payload.cruise_alt or 30.0),
        mission_type=MissionType.PRIVATE_PATROL,
        private_patrol=private_patrol,  # type: ignore[arg-type]
    )


async def _resolve_effective_payload(
    payload: PatrolSensorTriggerIn,
    *,
    db: AsyncSession,
    org_id: int | None,
    owner_id: int,
) -> tuple[PatrolSensorTriggerIn, dict[str, str] | None]:
    event_ctx = await resolve_event_trigger_payload(
        db,
        payload,
        org_id=org_id,
        owner_id=owner_id,
    )
    if event_ctx is not None:
        field_name = event_ctx.field.name if event_ctx.field is not None else None
        meta = {"field_name": field_name} if field_name else {}
        return event_ctx.effective_payload, meta or None

    resolved_ctx = await resolve_registered_sensor_trigger(
        db,
        payload,
        org_id=org_id,
        owner_id=owner_id,
    )
    if resolved_ctx is not None:
        meta = {
            "sensor_name": resolved_ctx.sensor.name,
            "site_name": resolved_ctx.site.name,
        }
        return resolved_ctx.effective_payload, meta

    if payload.geofence_polygon_lonlat is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No event-trigger setup found. Configure Property Patrol → Setup → Event Triggered "
                "with a saved property geofence, or include geofence_polygon_lonlat in the trigger payload."
            ),
        )

    sensor_id = (payload.sensor_id or "webhook").strip() or "webhook"
    effective = PatrolSensorTriggerIn(
        trigger_id=payload.trigger_id,
        sensor_id=sensor_id,
        field_id=payload.field_id,
        coordinates=payload.coordinates,
        mission_name=payload.mission_name,
        geofence_polygon_lonlat=payload.geofence_polygon_lonlat,
        sensor_registry=payload.sensor_registry,
        cruise_alt=payload.cruise_alt or 30.0,
        speed_mps=payload.speed_mps or 6.0,
        verification_loiter_s=payload.verification_loiter_s or 45.0,
        verification_radius_m=payload.verification_radius_m or 18.0,
        track_target=payload.track_target if payload.track_target is not None else True,
        search_grid_spacing_m=payload.search_grid_spacing_m or 40.0,
        search_grid_angle_deg=payload.search_grid_angle_deg or 0.0,
        target_label=payload.target_label,
        ai_tasks=payload.ai_tasks or list(PATROL_AI_TASKS),
    )
    return effective, None


async def dispatch_sensor_trigger(
    payload: PatrolSensorTriggerIn,
    *,
    user: Any,
    db: AsyncSession,
) -> PatrolSensorTriggerOut:
    trigger_id = str(payload.trigger_id).strip()
    org_id = getattr(user, "org_id", None)
    owner_id = int(user.id)
    logger.info(
        "Sensor trigger received trigger_id=%s sensor_id=%s org_id=%s owner_id=%s",
        trigger_id,
        payload.sensor_id,
        org_id,
        owner_id,
    )

    effective_payload, meta = await _resolve_effective_payload(
        payload,
        db=db,
        org_id=org_id,
        owner_id=owner_id,
    )

    sensor_id_for_receipt = (effective_payload.sensor_id or "webhook").strip() or "webhook"

    geofence = validate_geofence_polygon(effective_payload.geofence_polygon_lonlat)

    registry = _registry_from_payload(effective_payload.sensor_registry)
    resolved_ctx = await resolve_registered_sensor_trigger(
        db,
        payload,
        org_id=org_id,
        owner_id=owner_id,
    )
    if resolved_ctx is not None:
        registry.update(sensor_registry_from_sensor(resolved_ctx.sensor))

    trigger_coords: tuple[float, float] | None = None
    if effective_payload.coordinates is not None:
        trigger_coords = (
            float(effective_payload.coordinates[0]),
            float(effective_payload.coordinates[1]),
        )

    resolved = resolve_trigger_location(
        trigger_coordinates=trigger_coords,
        sensor_id=sensor_id_for_receipt,
        sensor_registry=registry,
    )
    response_mode = choose_response_mode(resolved)

    if resolved is not None:
        lon, lat = resolved
        if not validate_location_in_geofence(lon, lat, geofence):
            raise HTTPException(
                status_code=422,
                detail="Resolved trigger location is outside the configured geofence.",
            )

    mission = build_event_triggered_mission(
        effective_payload,
        response_mode=response_mode,
        resolved_location=resolved,
        geofence=geofence,
    )

    mission_name = (effective_payload.mission_name or "").strip() or f"Sensor trigger {trigger_id}"
    create_payload = _mission_create_payload(
        effective_payload,
        mission_name=mission_name,
        geofence=geofence,
    )
    profile = flight_profile_for_payload(create_payload)
    cruise_alt = float(effective_payload.cruise_alt or 30.0)
    geofence_waypoints = [
        Coordinate(lat=float(lat), lon=float(lon), alt=cruise_alt) for lon, lat in geofence
    ]

    orch = await get_orchestrator()
    await _ensure_drone_available(orch)

    async def _prepare_trigger_dispatch() -> Any:
        await _ensure_drone_ready_for_preflight(orch, profile=profile)
        return await orch._run_preflight_checks(
            mission.get_waypoints(),
            cruise_alt,
            raise_on_fail=False,
            mission_data=None,
            config_overrides={"FLIGHT_ENVIRONMENT": profile.environment.value},
            geofence_polygon=geofence_waypoints,
        )

    try:
        preflight = await asyncio.wait_for(
            _prepare_trigger_dispatch(),
            timeout=TRIGGER_DISPATCH_READY_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "Sensor trigger %s timed out after %.0fs waiting for drone/preflight",
            trigger_id,
            TRIGGER_DISPATCH_READY_TIMEOUT_S,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Drone is not ready for event-trigger dispatch. "
                "Ensure the simulator/vehicle is running, then retry."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Sensor trigger %s preflight execution failed", trigger_id)
        raise HTTPException(
            status_code=503,
            detail=f"Drone is not available for dispatch: {exc}",
        ) from exc

    overall = str(getattr(preflight, "overall_status", "") or "")
    if not preflight_allows_start(overall):
        summary = getattr(preflight, "summary", None) or {}
        failed = summary.get("failed") if isinstance(summary, dict) else None
        detail = f"Preflight checks failed for sensor trigger (status={overall})."
        if failed:
            detail = f"{detail} {failed} check(s) failed."
        logger.warning(
            "Sensor trigger %s rejected: preflight status=%s summary=%s",
            trigger_id,
            overall,
            getattr(preflight, "summary", None),
        )
        raise HTTPException(status_code=412, detail=detail)
    if overall == "WARN" and not ALLOW_WARN_PREFLIGHT_START:
        logger.warning(
            "Sensor trigger %s proceeding with preflight WARN (allow_warn disabled)",
            trigger_id,
        )

    if org_id is not None:
        existing = await get_trigger_receipt(
            db,
            org_id=int(org_id),
            trigger_id=trigger_id,
        )
        if existing is not None and existing.client_flight_id:
            logger.info(
                "Sensor trigger %s duplicate replay for flight %s",
                trigger_id,
                existing.client_flight_id,
            )
            return PatrolSensorTriggerOut(
                accepted=True,
                trigger_id=trigger_id,
                response_mode=existing.response_mode or response_mode,
                client_flight_id=existing.client_flight_id,
                message="Duplicate trigger_id; returning existing dispatched flight.",
                duplicate=True,
                sensor_name=meta.get("sensor_name") if meta else None,
                site_name=meta.get("site_name") if meta else None,
                field_name=meta.get("field_name") if meta else None,
            )

        claimed = await claim_trigger_receipt(
            db,
            org_id=int(org_id),
            trigger_id=trigger_id,
            sensor_id=sensor_id_for_receipt,
        )
        await db.commit()
        if not claimed:
            replay = await get_trigger_receipt(
                db,
                org_id=int(org_id),
                trigger_id=trigger_id,
            )
            if replay is not None and replay.client_flight_id:
                return PatrolSensorTriggerOut(
                    accepted=True,
                    trigger_id=trigger_id,
                    response_mode=replay.response_mode or response_mode,
                    client_flight_id=replay.client_flight_id,
                    message="Duplicate trigger_id; returning existing dispatched flight.",
                    duplicate=True,
                    sensor_name=meta.get("sensor_name") if meta else None,
                    site_name=meta.get("site_name") if meta else None,
                    field_name=meta.get("field_name") if meta else None,
                )
            raise HTTPException(
                status_code=409,
                detail="Trigger is already being processed; retry with a new trigger_id.",
            )

    client_flight_id = f"trigger_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    default_project_id = await mission_launch_service.default_project_id(org_id=org_id)

    try:
        orch.current_mission_name = mission_name
        orch.current_client_flight_id = client_flight_id
        orch.current_mission_type = MissionType.PRIVATE_PATROL.value
        orch.current_flight_environment = profile.environment.value
        orch.current_control_mode = profile.control_mode
        orch.current_mission_task_type = "event_triggered_patrol"
        orch.current_preflight_run_id = None

        await mission_application.create(
            client_flight_id=client_flight_id,
            user_id=owner_id,
            org_id=org_id,
            project_id=default_project_id,
            mission_name=mission_name,
            mission_type=MissionType.PRIVATE_PATROL.value,
            mission_task_type="event_triggered_patrol",
            private_patrol_task_type="event_triggered_patrol",
            preflight_run_uuid=None,
            ai_tasks=list(mission.ai_tasks),
            state="queued",
            mission_params={
                "trigger_id": trigger_id,
                "sensor_id": sensor_id_for_receipt,
                "response_mode": response_mode,
            },
        )

        from backend.modules.missions.api.routes import execute_mission

        task = asyncio.create_task(
            execute_mission(
                orch,
                mission,
                cruise_alt,
                mission_name,
                client_flight_id,
            )
        )
        orch._active_mission_task = task

        def _clear_active_mission_task(done_task: asyncio.Task) -> None:
            if getattr(orch, "_active_mission_task", None) is done_task:
                orch._active_mission_task = None

        task.add_done_callback(_clear_active_mission_task)

        if org_id is not None:
            await finalize_trigger_receipt(
                db,
                org_id=int(org_id),
                trigger_id=trigger_id,
                client_flight_id=client_flight_id,
                response_mode=response_mode,
            )
            await db.commit()
    except HTTPException:
        if org_id is not None:
            await release_trigger_receipt(db, org_id=int(org_id), trigger_id=trigger_id)
            await db.commit()
        raise
    except Exception as exc:
        if org_id is not None:
            await release_trigger_receipt(db, org_id=int(org_id), trigger_id=trigger_id)
            await db.commit()
        logger.exception("Sensor trigger %s dispatch failed after claim", trigger_id)
        raise HTTPException(
            status_code=500,
            detail=f"Sensor trigger dispatch failed: {exc}",
        ) from exc

    logger.info(
        "Sensor trigger %s dispatched flight %s mode=%s",
        trigger_id,
        client_flight_id,
        response_mode,
    )

    resolved_out = [float(resolved[0]), float(resolved[1])] if resolved else None
    return PatrolSensorTriggerOut(
        accepted=True,
        trigger_id=trigger_id,
        response_mode=response_mode,
        resolved_location_lonlat=resolved_out,
        client_flight_id=client_flight_id,
        message=(
            "Incident response flight dispatched."
            if response_mode == "incident_response"
            else "Detection/search flight dispatched."
        ),
        sensor_name=meta.get("sensor_name") if meta else None,
        site_name=meta.get("site_name") if meta else None,
        field_name=meta.get("field_name") if meta else None,
    )
