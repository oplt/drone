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
from backend.modules.missions.application import mission_application
from backend.modules.missions.flight_profile import FlightProfile
from backend.modules.missions.launch_service import mission_launch_service
from backend.modules.missions.schemas.mission_create import MissionCreateIn, MissionCreateOut
from backend.modules.missions.service.mission_builder import (
    build_mission,
    flight_profile_for_payload,
)
from backend.modules.vehicle_runtime.factory import get_orchestrator

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
        await asyncio.to_thread(orch.drone.get_telemetry)
        if getattr(getattr(orch, "drone", None), "vehicle", None) is not None:
            return
    except Exception:
        logger.info("Telemetry unavailable, attempting to connect drone for mission start")

    try:
        await asyncio.to_thread(
            orch.drone.connect,
            home_fallback_allowed=profile.allows_home_fallback,
        )
        await asyncio.to_thread(orch.drone.get_telemetry)
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
                    f"Preflight status '{rec.overall_status}' does not satisfy mission start policy."
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
            detail="Another mission is already running. Wait for it to complete before starting a new one.",
        )

    profile = flight_profile_for_payload(payload)
    try:
        await _ensure_drone_ready_for_preflight(orch, profile=profile)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Drone connection could not be established: {exc}",
        ) from exc

    orch.current_mission_name = payload.name
    orch.current_client_flight_id = client_flight_id
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
        mission_params={},
    )

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
