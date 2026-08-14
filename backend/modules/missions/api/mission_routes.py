from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.missions.api.mission_route_schemas import (
    MissionCreateIn,
    MissionCreateOut,
    MissionRuntimeOut,
    ResumableMissionOut,
    StateTransitionOut,
)
from backend.modules.missions.api.mission_runtime_mappers import (
    build_state_timeline,
    runtime_to_out,
)
from backend.modules.missions.api.runtime_dto import MissionRuntimeRecord, get_runtime_for_user
from backend.modules.missions.application import mission_application
from backend.modules.missions.service.command_applicator import (
    _sync_runtime_flight_id_from_orchestrator,
)
from backend.modules.missions.service.mission_start import start_mission_for_user
from backend.modules.vehicle_runtime.factory import get_orchestrator

router = APIRouter(tags=["tasks"])


@router.post("/missions", response_model=MissionCreateOut)
async def create_mission(
    payload: MissionCreateIn,
    user=Depends(require_user),
):
    return await start_mission_for_user(payload, user=user)


@router.get("/missions", response_model=Page[MissionRuntimeOut])
async def list_missions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await mission_application.list_recent(
        user_id=int(user.id), limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [runtime_to_out(MissionRuntimeRecord.from_db(row)) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )


@router.get("/missions/active", response_model=MissionRuntimeOut)
async def get_active_mission(
    user=Depends(require_user),
):
    db_row = await mission_application.get_active()
    if db_row is None:
        raise HTTPException(status_code=404, detail="No active mission")
    runtime = MissionRuntimeRecord.from_db(db_row)
    orch = await get_orchestrator()
    await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
    return runtime_to_out(runtime)


@router.get("/missions/resumable", response_model=Page[ResumableMissionOut])
async def list_resumable_missions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    page_limit = clamp_page_limit(limit, maximum=100)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await mission_application.list_resumable(
        user_id=int(user.id), limit=page_limit + 1, offset=page_offset
    )
    result = []
    for row in rows:
        ended_ts = row.ended_at.timestamp() if isinstance(row.ended_at, datetime) else None
        result.append(
            ResumableMissionOut(
                flight_id=row.client_flight_id,
                mission_name=row.mission_name,
                mission_type=row.mission_type,
                mission_task_type=row.mission_task_type or row.private_patrol_task_type,
                state=row.state,
                ended_at=ended_ts,
                failure_reason=row.failure_reason,
                resume_metadata=dict(row.resume_metadata or {}),
                mission_params=dict(row.mission_params or {}),
            )
        )
    return page_from_offset(result, limit=page_limit, offset=page_offset)


@router.get("/missions/{flight_id}", response_model=MissionRuntimeOut)
async def get_mission_runtime(
    flight_id: str,
    user=Depends(require_user),
):
    runtime = await get_runtime_for_user(flight_id, user_id=int(user.id))
    orch = await get_orchestrator()
    await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
    return runtime_to_out(runtime)


@router.get("/missions/{flight_id}/transitions", response_model=Page[StateTransitionOut])
async def get_mission_state_transitions(
    flight_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    db_row = await mission_application.get_by_client_id_for_user(flight_id, int(user.id))
    if db_row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    commands = await mission_application.list_commands(
        flight_id, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        build_state_timeline(db_row, commands),
        limit=page_limit,
        offset=page_offset,
    )
