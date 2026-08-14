from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.core.config.runtime import env_truthy, settings
from backend.core.database.session import Session
from backend.modules.missions.application import mission_application
from backend.modules.missions.flight_profile import FlightProfile
from backend.modules.missions.launch_service import mission_launch_service
from backend.modules.missions.schemas.mission_create import MissionCreateIn, MissionCreateOut
from backend.modules.missions.service.mission_builder import (
    build_mission,
    flight_profile_for_payload,
)
from backend.modules.vehicle_runtime.factory import get_orchestrator
from backend.modules.fields.service import field_service
from backend.modules.agriculture.service import agriculture_service
from backend.modules.agriculture.events import emit_agriculture_event
from backend.modules.agriculture.policy import agriculture_validator
from backend.modules.agriculture.workflow import snapshot_is_usable
from backend.modules.agriculture.workflow_models import AgricultureMissionPlan, AgriculturePreflightSnapshot
from sqlalchemy import select

logger = logging.getLogger(__name__)

REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION = env_truthy(settings.require_preflight_run_before_mission)
ALLOW_WARN_PREFLIGHT_START = env_truthy(settings.allow_warn_preflight_start)


def mission_fingerprint(payload: MissionCreateIn) -> str:
    canonical = payload.model_dump(mode="json", exclude={"preflight_run_id"})
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def preflight_allows_start(overall_status: str) -> bool:
    normalized = str(overall_status).upper()
    if normalized == "PASS":
        return True
    if normalized == "WARN":
        return ALLOW_WARN_PREFLIGHT_START
    return False


async def _get_preflight_run(run_id: str) -> Any | None:
    db_row = await mission_application.get_preflight(run_id)
    if db_row is None:
        return None
    if db_row.expires_at and db_row.expires_at < datetime.now(UTC):
        return None
    return db_row


async def _ensure_drone_ready_for_preflight(orch: Any, *, profile: FlightProfile) -> None:
    try:
        await orch.async_drone.get_telemetry()
        if orch.async_drone.vehicle is not None:
            return
    except Exception:
        logger.info("Telemetry unavailable, attempting to connect drone for mission start")

    try:
        await orch.async_drone.connect(
            home_fallback_allowed=profile.allows_home_fallback,
        )
        await orch.async_drone.get_telemetry()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Drone connection could not be established for "
                f"{profile.environment.value}: {exc}"
            ),
        ) from exc


async def start_mission_for_user(
    payload: MissionCreateIn,
    *,
    user: Any,
) -> MissionCreateOut:
    """Create and start a mission without coupling callers to HTTP route modules."""
    if payload.field_id is not None:
        async with Session() as validation_db:
            field = await field_service.get_owned(validation_db, field_id=payload.field_id, user=user)
            if field is None:
                raise HTTPException(status_code=404, detail="Agriculture field not found")
            if payload.agriculture is None:
                raise HTTPException(status_code=422, detail="field_id requires agriculture profile")
            try:
                agriculture_service.validate_profile(
                    profile=payload.agriculture,
                    cruise_alt_m=payload.cruise_alt,
                    field_polygon_lonlat=payload.grid.field_polygon_lonlat if payload.grid is not None else [],
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if payload.agriculture.plan_id or payload.agriculture.preflight_snapshot_id:
                plan = await validation_db.scalar(
                    select(AgricultureMissionPlan).where(
                        AgricultureMissionPlan.id == payload.agriculture.plan_id,
                        AgricultureMissionPlan.field_id == payload.field_id,
                        AgricultureMissionPlan.org_id == user.org_id,
                    )
                ) if payload.agriculture.plan_id else None
                if plan is None or plan.status != "validated":
                    raise HTTPException(status_code=412, detail={"code": "AGRICULTURE_PLAN_NOT_VALIDATED", "message": "A validated agriculture plan is required before launch"})
                saved_route = (plan.route_geojson or {}).get("coordinates") or []
                if payload.grid is not None and saved_route:
                    payload.grid.route_waypoints = [
                        {"lon": float(point[0]), "lat": float(point[1]), "alt": float(payload.grid.agl_m)}
                        for point in saved_route
                    ]
                snapshot = await validation_db.scalar(
                    select(AgriculturePreflightSnapshot).where(
                        AgriculturePreflightSnapshot.id == payload.agriculture.preflight_snapshot_id,
                        AgriculturePreflightSnapshot.plan_id == plan.id,
                        AgriculturePreflightSnapshot.org_id == user.org_id,
                    )
                ) if payload.agriculture.preflight_snapshot_id else None
                if snapshot is None or not snapshot_is_usable(snapshot):
                    raise HTTPException(status_code=412, detail={"code": "AGRICULTURE_PREFLIGHT_NOT_ACKNOWLEDGED", "message": "A passing, acknowledged agriculture preflight is required before launch"})
            await agriculture_service.get_or_create_profile(validation_db, field_id=payload.field_id, user=user)
    preflight_run_id = (payload.preflight_run_id or "").strip()
    if preflight_run_id:
        rec = await _get_preflight_run(preflight_run_id)
        if rec is None or rec.user_id != int(user.id):
            raise HTTPException(
                status_code=404,
                detail="Preflight run not found for this user.",
            )

        expected_fingerprint = mission_fingerprint(payload)
        if rec.mission_fingerprint != expected_fingerprint:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Preflight run does not match this mission payload. "
                    "Run preflight again before mission start."
                ),
            )

        if not preflight_allows_start(rec.overall_status):
            raise HTTPException(
                status_code=412,
                detail=(
                    f"Preflight status '{rec.overall_status}' does not satisfy "
                    "mission start policy."
                ),
            )
    elif REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION:
        raise HTTPException(
            status_code=412,
            detail=(
                "Preflight run is required before mission start. "
                "Call POST /tasks/preflight/run and provide preflight_run_id."
            ),
        )

    try:
        mission, wps_count = build_mission(payload, owner_id=int(user.id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.agriculture is not None and payload.grid is not None:
        route = mission.get_waypoints()
        validation = agriculture_validator.validate(
            profile=payload.agriculture,
            cruise_alt_m=payload.cruise_alt,
            field_polygon_lonlat=payload.grid.field_polygon_lonlat,
            route_lonlat=[[float(point.lon), float(point.lat)] for point in route],
        )
        if not validation.valid:
            raise HTTPException(status_code=422, detail="Agriculture route invalid: " + ", ".join(validation.errors))

    client_flight_id = f"flight_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    orch = await get_orchestrator()
    active_task = getattr(orch, "_active_mission_task", None)
    active_db_row = await mission_application.get_active()
    if active_db_row is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Another mission is already active "
                f"({active_db_row.client_flight_id}, state={active_db_row.state}). "
                "Wait for it to complete before starting a new one."
            ),
        )
    if active_task is not None and not active_task.done():
        raise HTTPException(
            status_code=409,
            detail=(
                "Another mission is already running. Wait for it to complete "
                "before starting a new one."
            ),
        )

    profile = flight_profile_for_payload(payload)
    try:
        await _ensure_drone_ready_for_preflight(orch, profile=profile)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Drone connection failed during mission preflight")
        raise HTTPException(
            status_code=503,
            detail="Drone connection could not be established",
        ) from exc

    orch.current_mission_name = payload.name
    orch.current_client_flight_id = client_flight_id
    orch.current_org_id = user.org_id
    orch.current_mission_type = payload.mission_type.value
    orch.current_flight_environment = profile.environment.value
    orch.current_control_mode = profile.control_mode
    orch.current_mission_task_type = (
        getattr(payload.private_patrol, "task_type", None)
        if payload.private_patrol is not None
        else None
    )
    orch.current_preflight_run_id = preflight_run_id or None

    default_project_id = await mission_launch_service.default_project_id(org_id=user.org_id)

    patrol_task_type = (
        getattr(payload.private_patrol, "task_type", None)
        if payload.private_patrol is not None
        else None
    )
    await mission_application.create(
        client_flight_id=client_flight_id,
        user_id=int(user.id),
        org_id=user.org_id,
        project_id=default_project_id,
        mission_name=payload.name,
        mission_type=payload.mission_type.value,
        mission_task_type=patrol_task_type,
        private_patrol_task_type=patrol_task_type,
        preflight_run_uuid=preflight_run_id or None,
        ai_tasks=list(getattr(payload.private_patrol, "ai_tasks", None) or []),
        state="queued",
        mission_params=payload.model_dump(mode="json"),
    )

    if payload.field_id is not None and payload.agriculture is not None:
        snapshot = {
            **payload.agriculture.model_dump(mode="json"),
            "snapshot_version": 1,
            "snapshot_created_at": datetime.now(UTC).isoformat(),
            "field_id": payload.field_id,
            "field_polygon_lonlat": payload.grid.field_polygon_lonlat if payload.grid is not None else [],
            "route_lonlat": [[float(point.lon), float(point.lat)] for point in route],
            "route_waypoint_count": len(route),
            "cruise_alt_m": float(payload.cruise_alt),
            "target_agl_m": float(payload.grid.agl_m) if payload.grid is not None else float(payload.cruise_alt),
            "grid": payload.grid.model_dump(mode="json") if payload.grid is not None else None,
        }
        snapshot_blob = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
        agriculture_flight = await agriculture_service.ensure_flight_for_mission(
            mission_id=client_flight_id,
            field_id=payload.field_id,
            org_id=user.org_id,
            profile=snapshot,
            season=payload.agriculture.season,
            flight_kind=payload.agriculture.flight_kind,
            profile_snapshot_hash=hashlib.sha256(snapshot_blob.encode("utf-8")).hexdigest(),
            status="running",
        )
        if payload.agriculture.preflight_snapshot_id:
            async with Session() as workflow_db:
                workflow_snapshot = await workflow_db.scalar(
                    select(AgriculturePreflightSnapshot).where(
                        AgriculturePreflightSnapshot.id == payload.agriculture.preflight_snapshot_id,
                        AgriculturePreflightSnapshot.plan_id == payload.agriculture.plan_id,
                        AgriculturePreflightSnapshot.org_id == user.org_id,
                    )
                )
                if workflow_snapshot is not None:
                    workflow_snapshot.flight_id = agriculture_flight.id
                    await workflow_db.commit()
        emit_agriculture_event("flight_started", flight_id=client_flight_id, field_id=payload.field_id)

    from backend.modules.missions.api.routes import execute_mission

    task = asyncio.create_task(
        execute_mission(
            orch,
            mission,
            payload.cruise_alt,
            payload.name,
            runtime_id=client_flight_id,
        )
    )
    orch._active_mission_task = task

    def _clear_active_mission_task(done_task: asyncio.Task) -> None:
        if getattr(orch, "_active_mission_task", None) is done_task:
            orch._active_mission_task = None

    task.add_done_callback(_clear_active_mission_task)

    return MissionCreateOut(
        flight_id=client_flight_id,
        status="queued",
        mission_name=payload.name,
        mission_type=payload.mission_type.value,
        waypoints_count=wps_count,
        preflight_run_id=preflight_run_id or None,
    )
