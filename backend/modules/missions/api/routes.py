from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from backend.core.config.runtime import env_truthy, settings
from backend.core.errors.public import public_error
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.infrastructure.jobs import enqueue_task
from backend.modules.deliverables.service import mission_export_service
from backend.modules.identity.dependencies import require_user
from backend.modules.missions.api.preview_routes import router as preview_router
from backend.modules.missions.api.runtime_dto import (
    MissionCommandAuditOut,
    MissionCommandAuditRecord,
    MissionRuntimeRecord,
    get_runtime_for_user,
    resolve_idempotency_key,
)
from backend.modules.missions.api.routes_commands import router as commands_router
from backend.modules.missions.service.command_applicator import (
    _sync_runtime_flight_id_from_orchestrator,
    apply_mission_command as _apply_mission_command,
)
from backend.modules.missions.api.runtime_routes import router as runtime_router
from backend.modules.missions.application import mission_application
from backend.modules.missions.domain.state_machine import (
    TERMINAL_STATES as _SM_TERMINAL_STATES,
    MissionLifecycleState,
)
from backend.modules.missions.domain.state_machine import (
    is_terminal as _sm_is_terminal,
)
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.schemas.mission_create import (
    MissionCreateIn,
    MissionCreateOut,
    PatrolTaskType,
    validate_private_patrol_task_inputs,
)
from backend.modules.missions.service.mission_builder import (
    _resolve_trigger_event_location,
    build_mission,
    flight_profile_for_payload,
)
from backend.modules.missions.service.mission_start import (
    _ensure_drone_ready_for_preflight,
    mission_fingerprint,
    preflight_allows_start,
    start_mission_for_user,
)
from backend.modules.patrol.planning import (
    PATROL_AI_TASKS,
    estimate_camera_trigger_distance_m,
    generate_event_triggered_patrol_plan,
    generate_grid_surveillance_plan,
    generate_private_patrol_plan,
    generate_waypoint_patrol_plan,
    normalize_ai_tasks,
    normalize_patrol_direction,
    private_patrol_task_catalog,
    repeat_patrol_loops,
)
from backend.modules.preflight.checks.schemas import PreflightReport
from backend.modules.vehicle_runtime.factory import get_orchestrator
from backend.modules.vehicle_runtime.vehicle_port import MissionAbortRequested
from backend.modules.warehouse.exceptions import WarehouseMissionFailure

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/tasks", tags=["tasks"])
router.include_router(preview_router)
router.include_router(runtime_router)
router.include_router(commands_router)

_MissionRuntimeRecord = MissionRuntimeRecord
_MissionCommandAudit = MissionCommandAuditRecord
_get_runtime_for_user = get_runtime_for_user
_resolve_idempotency_key = resolve_idempotency_key

PREFLIGHT_RUN_TTL_SECONDS = max(60, settings.preflight_run_ttl_seconds)
REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION = env_truthy(settings.require_preflight_run_before_mission)


async def _run_preflight_report(
    orch: Any,
    payload: MissionCreateIn,
    *,
    mission: Any,
    mission_data_override: dict[str, object] | None,
) -> PreflightReport:
    profile = flight_profile_for_payload(payload)
    await _ensure_drone_ready_for_preflight(orch, profile=profile)
    return await orch._run_preflight_checks(
        mission.get_waypoints(),
        payload.cruise_alt,
        raise_on_fail=False,
        mission_data=mission_data_override,
        config_overrides={"FLIGHT_ENVIRONMENT": profile.environment.value},
    )




class MissionRuntimeOut(BaseModel):
    flight_id: str
    mission_name: str
    mission_type: str
    mission_task_type: str | None = None
    state: str
    created_at: float
    updated_at: float
    preflight_run_id: str | None = None
    db_flight_id: str | None = None
    last_error: str | None = None


class StateTransitionOut(BaseModel):
    """Single entry in a mission's reconstructed state timeline."""

    state: str
    entered_at: float  # Unix timestamp
    trigger: str  # "mission_created" | "execution_started" | "command:<cmd>" | "execution_ended"
    command_id: str | None = None
    command: str | None = None
    reason: str | None = None


class ResumableMissionOut(BaseModel):
    """Terminal mission that has checkpointed progress and can be re-launched."""

    flight_id: str
    mission_name: str
    mission_type: str
    mission_task_type: str | None = None
    state: str
    ended_at: float | None = None
    failure_reason: str | None = None
    resume_metadata: dict
    mission_params: dict


class PreflightRunOut(BaseModel):
    preflight_run_id: str
    mission_fingerprint: str
    overall_status: str
    can_start_mission: bool
    created_at: float
    expires_at: float
    report: PreflightReport


class MissionPreflightOut(BaseModel):
    """Preflight detail for the audit timeline."""

    preflight_run_id: str
    overall_status: str
    base_checks: list[dict]
    mission_checks: list[dict]
    critical_failures: list[str]
    summary: dict
    started_at: float | None = None
    completed_at: float | None = None


class FlightEventOut(BaseModel):
    """Single flight event for the audit timeline."""

    id: int
    type: str
    data: dict
    created_at: float


@dataclass
class _PreflightRunRecord:
    run_id: str
    user_id: int
    mission_fingerprint: str
    overall_status: str
    created_at: float
    expires_at: float
    report: dict

    @classmethod
    def from_db(cls, row: Any) -> _PreflightRunRecord:
        """Build a value-object DTO from a PreflightRun ORM row."""
        created_ts = (
            row.created_at.timestamp()
            if isinstance(row.created_at, datetime)
            else float(row.created_at or 0)
        )
        expires_ts = (
            row.expires_at.timestamp()
            if isinstance(row.expires_at, datetime)
            else (created_ts + PREFLIGHT_RUN_TTL_SECONDS)
        )
        report_raw = {
            "mission_type": row.mission_type,
            "overall_status": row.overall_status,
            "base_checks": row.base_checks or [],
            "mission_checks": row.mission_checks or [],
            "critical_failures": [
                {"name": n, "status": "FAIL", "message": None}
                for n in (row.critical_failures or [])
            ],
            "summary": row.summary or {},
        }
        return cls(
            run_id=row.run_uuid,
            user_id=row.user_id or 0,
            mission_fingerprint=row.mission_fingerprint or "",
            overall_status=row.overall_status,
            created_at=created_ts,
            expires_at=expires_ts,
            report=report_raw,
        )


TERMINAL_MISSION_STATES = _SM_TERMINAL_STATES


# ---------------------------------------------------------------------------
# Mission runtime lifecycle store
# ---------------------------------------------------------------------------

# Legacy TTL / history constants kept so any external env vars still parse cleanly.
# They are no longer used for in-memory eviction — the DB is authoritative.
MISSION_RUNTIME_TTL_SECONDS = max(600, settings.mission_runtime_ttl_seconds)
MISSION_RUNTIME_MAX_HISTORY = max(20, settings.mission_runtime_max_history)


def _is_terminal_state(state: str) -> bool:
    return _sm_is_terminal(str(state).lower())


def _db_status_for_runtime_state(state: MissionLifecycleState) -> FlightStatus:
    _map = {
        "planned": FlightStatus.ACTIVE,
        "preflight": FlightStatus.ACTIVE,
        "queued": FlightStatus.ACTIVE,
        "arming": FlightStatus.ACTIVE,
        "airborne": FlightStatus.ACTIVE,
        "running": FlightStatus.ACTIVE,  # legacy
        "paused": FlightStatus.PAUSED,
        "resumed": FlightStatus.ACTIVE,
        "aborting": FlightStatus.INTERRUPTED,
        "aborted": FlightStatus.INTERRUPTED,
        "completed": FlightStatus.COMPLETED,
        "failed": FlightStatus.FAILED,
    }
    return _map.get(str(state), FlightStatus.FAILED)


def _runtime_to_out(rec: _MissionRuntimeRecord) -> MissionRuntimeOut:
    private_patrol_task_type = getattr(rec, "private_patrol_task_type", None)
    mission_task_type = getattr(rec, "mission_task_type", None)
    return MissionRuntimeOut(
        flight_id=rec.client_flight_id,
        mission_name=rec.mission_name,
        mission_type=rec.mission_type,
        mission_task_type=(private_patrol_task_type or mission_task_type or None),
        state=rec.state,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        preflight_run_id=rec.preflight_run_id,
        db_flight_id=str(rec.db_flight_id) if rec.db_flight_id is not None else None,
        last_error=rec.last_error,
    )


def _audit_to_out(audit: _MissionCommandAudit) -> MissionCommandAuditOut:
    return MissionCommandAuditOut(
        command_id=audit.command_id,
        command=audit.command,
        idempotency_key=audit.idempotency_key,
        requested_by_user_id=audit.requested_by_user_id,
        requested_at=audit.requested_at,
        state_before=audit.state_before,
        state_after=audit.state_after,
        accepted=audit.accepted,
        message=audit.message,
        reason=audit.reason,
    )


# Stale in-memory cleanup is no longer needed — DB is the store.


async def _set_runtime_state(
    runtime_id: str,
    *,
    state: MissionLifecycleState,
    error: str | None = None,
) -> None:
    await mission_application.set_state(runtime_id, state=state, error=error)


# ---------------------------------------------------------------------------
# Preflight store helpers (DB-backed)
# ---------------------------------------------------------------------------


async def _store_preflight_run(
    *,
    user_id: int,
    mission_fingerprint: str,
    report: PreflightReport,
) -> _PreflightRunRecord:
    now = time.time()
    run_uuid = f"pf_{int(now)}_{uuid.uuid4().hex[:10]}"
    report_dump = report.model_dump(mode="json")
    expires_at_dt = datetime.fromtimestamp(now + PREFLIGHT_RUN_TTL_SECONDS, tz=UTC)
    db_row = await mission_application.create_preflight(
        run_uuid=run_uuid,
        user_id=user_id,
        mission_type=str(report.mission_type or ""),
        mission_name=None,
        mission_fingerprint=mission_fingerprint,
        overall_status=str(report.overall_status),
        base_checks=report_dump.get("base_checks", []),
        mission_checks=report_dump.get("mission_checks", []),
        critical_failures=[c["name"] for c in (report_dump.get("critical_failures") or [])],
        summary=report_dump.get("summary") or {},
        expires_at=expires_at_dt,
        completed_at=datetime.now(UTC),
    )
    return _PreflightRunRecord.from_db(db_row)


async def _get_preflight_run(run_id: str) -> _PreflightRunRecord | None:
    db_row = await mission_application.get_preflight(run_id)
    if db_row is None:
        return None
    # Enforce TTL in application layer for safety.
    if db_row.expires_at and db_row.expires_at < datetime.now(UTC):
        return None
    return _PreflightRunRecord.from_db(db_row)


def _preflight_record_out(rec: _PreflightRunRecord) -> PreflightRunOut:
    return PreflightRunOut(
        preflight_run_id=rec.run_id,
        mission_fingerprint=rec.mission_fingerprint,
        overall_status=rec.overall_status,
        can_start_mission=preflight_allows_start(rec.overall_status),
        created_at=rec.created_at,
        expires_at=rec.expires_at,
        report=PreflightReport.model_validate(rec.report),
    )


async def execute_mission(
    orch: Any,
    mission: Any,  # Any object with .execute(orch, alt=…) method
    cruise_alt: float,
    mission_name: str,
    runtime_id: str,
) -> None:
    """Run any mission that implements .execute(orch, *, alt)."""
    reconcile_db_flight_id: int | None = None
    reconcile_db_status: FlightStatus | None = None
    reconcile_note: str = ""
    terminal_state: MissionLifecycleState = "completed"
    terminal_error: str | None = None
    await _set_runtime_state(runtime_id, state="airborne")
    try:
        await mission.execute(orch, alt=cruise_alt)
        logger.info("✅ Mission '%s' completed successfully", mission_name)
    except MissionAbortRequested as exc:
        terminal_state = "aborted"
        terminal_error = str(exc)
        logger.warning("🛑 Mission '%s' aborted: %s", mission_name, exc)
    except WarehouseMissionFailure as exc:
        terminal_error = str(exc.message or exc)
        if exc.stage == "capture" and exc.action == "complete":
            terminal_state = "completed"
            logger.warning(
                "⚠️ Mission '%s' flight completed with mapping failure: %s",
                mission_name,
                exc.message or exc,
            )
        else:
            terminal_state = "failed"
            logger.warning("🛑 Mission '%s' failed: %s", mission_name, exc)
    except asyncio.CancelledError:
        terminal_state = "failed"
        terminal_error = "Mission task cancelled unexpectedly"
        logger.exception(
            "Mission execution was cancelled",
            extra={"mission_id": runtime_id},
        )
    except Exception as exc:
        terminal_state = "failed"
        terminal_error = str(exc)
        logger.exception(
            "Mission execution failed",
            extra={"mission_id": runtime_id},
        )
    finally:
        db_row = await mission_application.finalize_execution(
            runtime_id,
            state=terminal_state,
            error=terminal_error,
        )
        try:
            from backend.modules.agriculture.service import agriculture_service

            await agriculture_service.reconcile_mission_terminal_state(
                mission_id=runtime_id,
                mission_state=terminal_state,
            )
        except Exception:
            logger.exception(
                "Failed reconciling agriculture lifecycle for mission %s",
                runtime_id,
            )
        if db_row is not None:
            runtime = _MissionRuntimeRecord.from_db(db_row)
            await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
            if runtime.db_flight_id is not None and _is_terminal_state(runtime.state):
                reconcile_db_flight_id = runtime.db_flight_id
                reconcile_db_status = _db_status_for_runtime_state(runtime.state)
                reconcile_note = (
                    f"Mission {runtime.state}: {runtime.last_error}"
                    if runtime.last_error
                    else f"Mission {runtime.state}"
                )
                if runtime.state in {"completed", "failed", "aborted"}:
                    try:
                        from backend.modules.agents.hooks import (
                            schedule_postflight_for_mission_type,
                        )

                        schedule_postflight_for_mission_type(
                            runtime.mission_type,
                            mission_runtime_id=db_row.id,
                            client_flight_id=runtime_id,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to schedule postflight agents for %s",
                            runtime.mission_type,
                        )

        if reconcile_db_flight_id is not None and reconcile_db_status is not None:
            safe_note = (
                reconcile_note[:250] if reconcile_note else f"Mission {reconcile_db_status.value}"
            )
            try:
                await mission_application.finish_operational_flight(
                    orch.repo,
                    reconcile_db_flight_id,
                    status=reconcile_db_status,
                    note=safe_note,
                )
            except Exception:
                logger.exception(
                    "Failed reconciling terminal flight status to %s for db_flight_id=%s",
                    reconcile_db_status.value,
                    reconcile_db_flight_id,
                )
        if getattr(orch, "current_client_flight_id", None) == runtime_id:
            orch.current_client_flight_id = None
            orch.current_mission_name = None
            orch.current_mission_type = None
            orch.current_flight_environment = None
            orch.current_control_mode = None
            orch.current_mission_task_type = None
            orch.current_preflight_run_id = None


# Endpoints
# ---------------------------------------------------------------------------


@router.post("/preflight/run", response_model=PreflightRunOut)
async def run_preflight(
    payload: MissionCreateIn,
    user=Depends(require_user),
):
    """Run preflight checks as a first-class API call and store a short-lived run token."""
    try:
        mission, _ = build_mission(payload, owner_id=int(user.id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Mission inputs are invalid.") from exc

    orch = await get_orchestrator()
    active_task = getattr(orch, "_active_mission_task", None)
    if active_task is not None and not active_task.done():
        raise HTTPException(
            status_code=409,
            detail="Cannot run manual preflight while a mission is currently active.",
        )

    try:
        preflight_data_fn = getattr(mission, "get_preflight_mission_data", None)
        mission_data_override = preflight_data_fn() if callable(preflight_data_fn) else None
        report = await _run_preflight_report(
            orch,
            payload,
            mission=mission,
            mission_data_override=mission_data_override,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Manual preflight run failed",
            extra={"user_id": int(user.id), "mission_id": payload.name},
        )
        raise public_error(500, "PREFLIGHT_FAILED", "Preflight execution failed") from exc

    rec = await _store_preflight_run(
        user_id=int(user.id),
        mission_fingerprint=mission_fingerprint(payload),
        report=report,
    )
    return _preflight_record_out(rec)


@router.get("/preflight/runs/{preflight_run_id}", response_model=PreflightRunOut)
async def get_preflight_run(
    preflight_run_id: str,
    user=Depends(require_user),
):
    rec = await _get_preflight_run(preflight_run_id)
    if rec is None or rec.user_id != int(user.id):
        raise HTTPException(status_code=404, detail="Preflight run not found")
    return _preflight_record_out(rec)


@router.post("/missions", response_model=MissionCreateOut)
async def create_mission(
    payload: MissionCreateIn,
    user=Depends(require_user),
):
    """Create and start a mission — returns flight_id for WebSocket tracking."""
    return await start_mission_for_user(payload, user=user)



def _build_state_timeline(
    row: Any,
    commands: list,
) -> list[StateTransitionOut]:
    """Reconstruct a best-effort state timeline from a MissionRuntime DB row
    and its ordered OperatorCommand records."""
    events: list[tuple[float, StateTransitionOut]] = []

    # Initial state at creation.
    created_ts = row.created_at.timestamp() if isinstance(row.created_at, datetime) else 0.0
    events.append(
        (
            created_ts,
            StateTransitionOut(
                state=row.state if row.started_at is None and row.ended_at is None else "queued",
                entered_at=created_ts,
                trigger="mission_created",
            ),
        )
    )

    # Mission became airborne (started_at set on first running/airborne transition).
    if row.started_at is not None:
        started_ts = (
            row.started_at.timestamp()
            if isinstance(row.started_at, datetime)
            else float(row.started_at)
        )
        events.append(
            (
                started_ts,
                StateTransitionOut(
                    state="airborne",
                    entered_at=started_ts,
                    trigger="execution_started",
                ),
            )
        )

    # Operator command-driven transitions (accepted only).
    for cmd in commands:
        if not cmd.accepted:
            continue
        ts = (
            cmd.requested_at.timestamp()
            if isinstance(cmd.requested_at, datetime)
            else float(cmd.requested_at or 0)
        )
        events.append(
            (
                ts,
                StateTransitionOut(
                    state=cmd.state_after,
                    entered_at=ts,
                    trigger=f"command:{cmd.command}",
                    command_id=cmd.command_id,
                    command=cmd.command,
                    reason=cmd.reason,
                ),
            )
        )

    # Terminal state reached by execution path (not by a command).
    if row.ended_at is not None and _is_terminal_state(row.state):
        ended_ts = (
            row.ended_at.timestamp() if isinstance(row.ended_at, datetime) else float(row.ended_at)
        )
        # Only add if not already recorded via a command.
        last_cmd_states = {e.state for _, e in events if e.command_id}
        if row.state not in last_cmd_states:
            events.append(
                (
                    ended_ts,
                    StateTransitionOut(
                        state=row.state,
                        entered_at=ended_ts,
                        trigger="execution_ended",
                        reason=row.failure_reason if row.failure_reason else None,
                    ),
                )
            )

    events.sort(key=lambda x: x[0])
    return [e for _, e in events]


@router.get("/missions", response_model=Page[MissionRuntimeOut])
async def list_missions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    """List recent mission runtimes for the current user (newest first)."""
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await mission_application.list_recent(
        user_id=int(user.id), limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [_runtime_to_out(_MissionRuntimeRecord.from_db(r)) for r in rows],
        limit=page_limit,
        offset=page_offset,
    )


@router.get("/missions/active", response_model=MissionRuntimeOut)
async def get_active_mission(
    user=Depends(require_user),
):
    """Return the currently active mission runtime, or 404 if none is running."""
    db_row = await mission_application.get_active()
    if db_row is None:
        raise HTTPException(status_code=404, detail="No active mission")
    runtime = _MissionRuntimeRecord.from_db(db_row)
    orch = await get_orchestrator()
    await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
    return _runtime_to_out(runtime)


@router.get("/missions/resumable", response_model=Page[ResumableMissionOut])
async def list_resumable_missions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    """List terminal missions that have checkpointed progress and can be re-launched.

    A mission is resumable when it ended in ``failed`` or ``aborted`` state and
    its ``resume_metadata`` contains at least one checkpoint key that a mission
    executor can use to skip already-completed work.
    """
    page_limit = clamp_page_limit(limit, maximum=100)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await mission_application.list_resumable(
        user_id=int(user.id), limit=page_limit + 1, offset=page_offset
    )
    result = []
    for r in rows:
        ended_ts = r.ended_at.timestamp() if isinstance(r.ended_at, datetime) else None
        result.append(
            ResumableMissionOut(
                flight_id=r.client_flight_id,
                mission_name=r.mission_name,
                mission_type=r.mission_type,
                mission_task_type=r.mission_task_type or r.private_patrol_task_type,
                state=r.state,
                ended_at=ended_ts,
                failure_reason=r.failure_reason,
                resume_metadata=dict(r.resume_metadata or {}),
                mission_params=dict(r.mission_params or {}),
            )
        )
    return page_from_offset(result, limit=page_limit, offset=page_offset)


@router.get("/missions/{flight_id}", response_model=MissionRuntimeOut)
async def get_mission_runtime(
    flight_id: str,
    user=Depends(require_user),
):
    runtime = await _get_runtime_for_user(flight_id, user_id=int(user.id))
    orch = await get_orchestrator()
    await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
    return _runtime_to_out(runtime)


@router.get("/missions/{flight_id}/transitions", response_model=Page[StateTransitionOut])
async def get_mission_state_transitions(
    flight_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    """Return a chronological timeline of state transitions for a mission.

    The timeline is reconstructed from the mission's timestamps (``created_at``,
    ``started_at``, ``ended_at``) and the accepted operator command records.
    It is a best-effort view — internal transitions not driven by commands
    (e.g. queued → airborne) are inferred from timestamps, not recorded as
    discrete events.
    """
    db_row = await mission_application.get_by_client_id_for_user(flight_id, int(user.id))
    if db_row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    commands = await mission_application.list_commands(
        flight_id, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        _build_state_timeline(db_row, commands),
        limit=page_limit,
        offset=page_offset,
    )


class PrivatePatrolTaskTemplateOut(BaseModel):
    id: str
    label: str
    purpose: str
    description: str
    default_params: dict
    ai_tasks: list[str]


class PrivatePatrolTaskCatalogOut(BaseModel):
    mission_category: str
    tasks: list[PrivatePatrolTaskTemplateOut]


class PrivatePatrolPreviewIn(BaseModel):
    task_type: Literal[
        "perimeter_patrol",
        "waypoint_patrol",
        "grid_surveillance",
        "event_triggered_patrol",
    ] = "perimeter_patrol"
    property_polygon_lonlat: list[list[float]] | None = Field(default=None, min_length=3)
    key_points_lonlat: list[list[float]] | None = Field(default=None, min_length=2)
    cruise_alt: float = Field(default=30.0, gt=0, le=500.0)
    path_offset_m: float = Field(default=15.0, ge=0.0, le=120.0)
    direction: Literal["clockwise", "counterclockwise"] = "clockwise"
    patrol_loops: int = Field(default=1, ge=1, le=200)
    speed_mps: float = Field(default=6.0, ge=0.5, le=20.0)
    start_after_minutes: int = Field(default=0, ge=0, le=1440)
    repeat_interval_minutes: int = Field(default=0, ge=0, le=1440)
    camera_angle_deg: float = Field(default=35.0, ge=0.0, le=90.0)
    camera_overlap_pct: float = Field(default=50.0, ge=0.0, le=95.0)
    max_segment_length_m: float = Field(default=20.0, gt=1.0, le=300.0)
    hover_time_s: float = Field(default=15.0, ge=1.0, le=300.0)
    camera_scan_yaw_deg: float = Field(default=360.0, ge=0.0, le=360.0)
    zoom_capture: bool = True
    return_to_start: bool = True
    grid_spacing_m: float = Field(default=40.0, gt=1.0, le=300.0)
    grid_angle_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    safety_inset_m: float = Field(default=2.0, ge=0.0, le=100.0)
    grid_pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    grid_crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0.0, lt=180.0)
    grid_lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    grid_start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    grid_row_stride: int = Field(default=1, ge=1, le=20)
    grid_row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)
    trigger_event_location_lonlat: list[float] | None = Field(
        default=None, min_length=2, max_length=2
    )
    target_label: str | None = Field(default=None, max_length=120)
    verification_loiter_s: float = Field(default=45.0, ge=0.0, le=600.0)
    verification_radius_m: float = Field(default=18.0, ge=0.0, le=150.0)
    track_target: bool = True
    auto_stream_video: bool = True
    record_video_stream: bool = True
    ai_tasks: list[PatrolTaskType] = Field(default_factory=lambda: list(PATROL_AI_TASKS))

    @model_validator(mode="after")
    def _validate_by_task(self) -> PrivatePatrolPreviewIn:
        validate_private_patrol_task_inputs(
            task_type=self.task_type,
            property_polygon_lonlat=self.property_polygon_lonlat,
            key_points_lonlat=self.key_points_lonlat,
        )
        return self


class PrivatePatrolPreviewOut(BaseModel):
    waypoints: list[dict]
    work_leg_mask: list[bool]
    stats: dict
    camera: dict
    ai_tasks: list[str]


@router.get(
    "/missions/private-patrol/tasks",
    response_model=PrivatePatrolTaskCatalogOut,
)
async def get_private_patrol_tasks() -> PrivatePatrolTaskCatalogOut:
    return PrivatePatrolTaskCatalogOut(
        mission_category="private_patrol",
        tasks=[
            PrivatePatrolTaskTemplateOut.model_validate(item)
            for item in private_patrol_task_catalog()
        ],
    )


@router.post("/missions/private-patrol/preview", response_model=PrivatePatrolPreviewOut)
async def preview_private_patrol(
    payload: PrivatePatrolPreviewIn,
) -> PrivatePatrolPreviewOut:
    try:
        ai_tasks = normalize_ai_tasks(payload.ai_tasks)
        if payload.task_type == "event_triggered_patrol":
            resolved = _resolve_trigger_event_location(
                trigger_event_location_lonlat=payload.trigger_event_location_lonlat,
                property_polygon_lonlat=payload.property_polygon_lonlat,
            )
            if resolved is not None:
                plan = generate_event_triggered_patrol_plan(
                    resolved,
                    altitude_agl_m=float(payload.cruise_alt),
                    verification_radius_m=float(payload.verification_radius_m),
                    geofence_polygon_lonlat=[
                        tuple(pt) for pt in (payload.property_polygon_lonlat or [])
                    ],
                )
            else:
                polygon = [tuple(pt) for pt in (payload.property_polygon_lonlat or [])]
                plan = generate_grid_surveillance_plan(
                    polygon,
                    altitude_agl_m=float(payload.cruise_alt),
                    grid_spacing_m=float(payload.grid_spacing_m),
                    grid_angle_deg=float(payload.grid_angle_deg),
                    safety_inset_m=float(payload.safety_inset_m),
                    pattern_mode=payload.grid_pattern_mode,
                    crosshatch_angle_offset_deg=float(payload.grid_crosshatch_angle_offset_deg),
                    lane_strategy=payload.grid_lane_strategy,
                    start_corner=payload.grid_start_corner,
                    row_stride=int(payload.grid_row_stride),
                    row_phase_m=float(payload.grid_row_phase_m),
                )
            waypoints = plan.waypoints
        elif payload.task_type == "grid_surveillance":
            polygon = [tuple(pt) for pt in (payload.property_polygon_lonlat or [])]
            plan = generate_grid_surveillance_plan(
                polygon,
                altitude_agl_m=float(payload.cruise_alt),
                grid_spacing_m=float(payload.grid_spacing_m),
                grid_angle_deg=float(payload.grid_angle_deg),
                safety_inset_m=float(payload.safety_inset_m),
                pattern_mode=payload.grid_pattern_mode,
                crosshatch_angle_offset_deg=float(payload.grid_crosshatch_angle_offset_deg),
                lane_strategy=payload.grid_lane_strategy,
                start_corner=payload.grid_start_corner,
                row_stride=int(payload.grid_row_stride),
                row_phase_m=float(payload.grid_row_phase_m),
            )
            waypoints = plan.waypoints
        elif payload.task_type == "waypoint_patrol":
            key_points = [tuple(pt) for pt in (payload.key_points_lonlat or [])]
            plan = generate_waypoint_patrol_plan(
                key_points,
                altitude_agl_m=float(payload.cruise_alt),
                return_to_start=bool(payload.return_to_start),
            )
            waypoints = plan.waypoints
        else:
            direction = normalize_patrol_direction(payload.direction)
            polygon = [tuple(pt) for pt in (payload.property_polygon_lonlat or [])]
            plan = generate_private_patrol_plan(
                polygon,
                altitude_agl_m=float(payload.cruise_alt),
                path_offset_m=float(payload.path_offset_m),
                direction=direction,
                max_segment_length_m=float(payload.max_segment_length_m),
            )
            waypoints = repeat_patrol_loops(plan.waypoints, loops=int(payload.patrol_loops))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Patrol planning inputs are invalid.") from exc

    total_route_m = 0.0
    if len(waypoints) >= 2:
        for a, b in pairwise(waypoints):
            total_route_m += math.hypot(
                (float(b.lat) - float(a.lat)) * 111_132.0,
                (float(b.lon) - float(a.lon))
                * 111_320.0
                * math.cos(math.radians((float(a.lat) + float(b.lat)) / 2.0)),
            )
    mask_len = max(0, len(waypoints) - 1)

    if payload.task_type == "waypoint_patrol":
        key_points_count = len(payload.key_points_lonlat or [])
        hover_total_s = float(payload.hover_time_s) * float(key_points_count)
        est_duration_s = (total_route_m / max(0.1, float(payload.speed_mps))) + hover_total_s
        stats = {
            **plan.stats,
            "task_type": payload.task_type,
            "key_points": key_points_count,
            "waypoints": len(waypoints),
            "hover_time_s": float(payload.hover_time_s),
            "hover_total_s": round(hover_total_s, 1),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "speed_mps": float(payload.speed_mps),
        }
        return PrivatePatrolPreviewOut(
            waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
            work_leg_mask=[True] * mask_len,
            stats=stats,
            camera={
                "scan_yaw_deg": float(payload.camera_scan_yaw_deg),
                "zoom_capture": bool(payload.zoom_capture),
            },
            ai_tasks=[str(task) for task in ai_tasks],
        )

    if payload.task_type == "event_triggered_patrol":
        response_mode = (
            "incident_response"
            if payload.trigger_event_location_lonlat
            and len(payload.trigger_event_location_lonlat) == 2
            else "detection_search"
        )
        travel_s = total_route_m / max(0.1, float(payload.speed_mps))
        est_duration_s = travel_s + float(payload.verification_loiter_s)
        stats = {
            **plan.stats,
            "task_type": payload.task_type,
            "response_mode": response_mode,
            "waypoints": len(waypoints),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "verification_loiter_s": float(payload.verification_loiter_s),
            "speed_mps": float(payload.speed_mps),
        }
        return PrivatePatrolPreviewOut(
            waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
            work_leg_mask=[True] * mask_len,
            stats=stats,
            camera={
                "stream_to_operator": bool(payload.auto_stream_video),
                "track_target": bool(payload.track_target),
                "target_label": payload.target_label,
            },
            ai_tasks=[str(task) for task in ai_tasks],
        )

    if payload.task_type == "grid_surveillance":
        est_duration_s = total_route_m / max(0.1, float(payload.speed_mps))
        stats = {
            **plan.stats,
            "task_type": payload.task_type,
            "waypoints": len(waypoints),
            "total_route_m": round(total_route_m, 1),
            "estimated_duration_s": round(est_duration_s, 1),
            "speed_mps": float(payload.speed_mps),
        }
        return PrivatePatrolPreviewOut(
            waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
            work_leg_mask=[True] * mask_len,
            stats=stats,
            camera={
                "mode": "wide_coverage",
                "grid_spacing_m": float(payload.grid_spacing_m),
                "record_video_stream": bool(payload.record_video_stream),
            },
            ai_tasks=[str(task) for task in ai_tasks],
        )

    est_duration_s = total_route_m / max(0.1, float(payload.speed_mps))
    trigger_distance_m = estimate_camera_trigger_distance_m(
        altitude_agl_m=float(payload.cruise_alt),
        overlap_pct=float(payload.camera_overlap_pct),
    )
    stats = {
        **plan.stats,
        "task_type": payload.task_type,
        "patrol_loops": int(payload.patrol_loops),
        "waypoints": len(waypoints),
        "total_route_m": round(total_route_m, 1),
        "estimated_duration_s": round(est_duration_s, 1),
        "speed_mps": float(payload.speed_mps),
    }
    return PrivatePatrolPreviewOut(
        waypoints=[{"lat": w.lat, "lon": w.lon} for w in waypoints],
        work_leg_mask=[True] * mask_len,
        stats=stats,
        camera={
            "angle_deg": float(payload.camera_angle_deg),
            "overlap_pct": float(payload.camera_overlap_pct),
            "trigger_distance_m": round(trigger_distance_m, 2),
        },
        ai_tasks=[str(task) for task in ai_tasks],
    )


# ---------------------------------------------------------------------------
# Audit timeline endpoints
# ---------------------------------------------------------------------------


@router.get("/missions/{flight_id}/preflight", response_model=MissionPreflightOut)
async def get_mission_preflight(
    flight_id: str,
    user=Depends(require_user),
):
    """Return the preflight run result for a mission (audit timeline)."""
    db_row = await mission_application.get_by_client_id_for_user(flight_id, int(user.id))
    if db_row is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    preflight_run_id = getattr(db_row, "preflight_run_id", None)
    if not preflight_run_id:
        raise HTTPException(status_code=404, detail="No preflight run recorded for this mission")

    preflight_row = await mission_application.get_preflight(preflight_run_id)
    if preflight_row is None:
        raise HTTPException(status_code=404, detail="Preflight run not found")

    started_ts = preflight_row.started_at.timestamp() if preflight_row.started_at else None
    completed_ts = preflight_row.completed_at.timestamp() if preflight_row.completed_at else None

    return MissionPreflightOut(
        preflight_run_id=preflight_row.run_uuid,
        overall_status=preflight_row.overall_status,
        base_checks=preflight_row.base_checks or [],
        mission_checks=preflight_row.mission_checks or [],
        critical_failures=preflight_row.critical_failures or [],
        summary=preflight_row.summary or {},
        started_at=started_ts,
        completed_at=completed_ts,
    )


@router.get("/missions/{flight_id}/events", response_model=Page[FlightEventOut])
async def get_mission_flight_events(
    flight_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    """Return flight events for a mission in chronological order (audit timeline)."""
    db_row = await mission_application.get_by_client_id_for_user(flight_id, int(user.id))
    if db_row is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    db_flight_id = getattr(db_row, "flight_id", None)
    if db_flight_id is None:
        return Page(items=[])

    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    events = await mission_application.list_events(
        flight_id=db_flight_id, limit=page_limit + 1, offset=page_offset
    )

    items = [
        FlightEventOut(
            id=ev.id,
            type=ev.type,
            data=ev.data or {},
            created_at=ev.created_at.timestamp() if ev.created_at else 0.0,
        )
        for ev in events
    ]
    return page_from_offset(items, limit=page_limit, offset=page_offset)


# ---------------------------------------------------------------------------
# Export routes
# ---------------------------------------------------------------------------


@router.post("/missions/{flight_id}/export")
async def start_mission_export(
    flight_id: str,
    user=Depends(require_user),
):
    job = await mission_export_service.create_for_user(flight_id=flight_id, user=user)
    if job is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    enqueue_task(
        "backend.tasks.export_tasks.generate_mission_export",
        queue="exports",
        flight_id=flight_id,
        user_id=user.id,
        org_id=user.org_id,
        job_id=job.id,
    )
    return {"job_id": job.id}


@router.get("/missions/{flight_id}/export/{job_id}")
async def get_mission_export_status(
    flight_id: str,
    job_id: int,
    user=Depends(require_user),
):
    job = await mission_export_service.get_for_user(flight_id=flight_id, job_id=job_id, user=user)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    return {
        "job_id": job.id,
        "status": job.status,
        "download_url": job.download_url,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
