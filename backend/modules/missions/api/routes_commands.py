"""Mission operator command routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Query

from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.missions.api.runtime_dto import (
    MissionCommand,
    MissionCommandAuditOut,
    MissionCommandIn,
    MissionCommandOut,
    get_runtime_for_user,
    resolve_idempotency_key,
)
from backend.modules.missions.application import mission_application
from backend.modules.missions.service.command_applicator import apply_mission_command
from backend.modules.vehicle_runtime.factory import get_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


@router.get("/missions/{flight_id}/commands", response_model=Page[MissionCommandAuditOut])
async def get_mission_command_audit(
    flight_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
):
    await get_runtime_for_user(flight_id, user_id=int(user.id))
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await mission_application.list_commands(
        flight_id, limit=page_limit + 1, offset=page_offset
    )
    items = [
        MissionCommandAuditOut(
            command_id=row.command_id,
            command=row.command,
            idempotency_key=row.idempotency_key,
            requested_by_user_id=row.requested_by_user_id or 0,
            requested_at=row.requested_at.timestamp() if row.requested_at else 0.0,
            state_before=row.state_before,
            state_after=row.state_after,
            accepted=row.accepted,
            message=row.message,
            reason=row.reason,
        )
        for row in rows
    ]
    return page_from_offset(items, limit=page_limit, offset=page_offset)


@router.post(
    "/missions/{flight_id}/commands/{command}",
    response_model=MissionCommandOut,
)
async def issue_mission_command(
    flight_id: str,
    command: MissionCommand,
    payload: MissionCommandIn,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(require_user),
):
    runtime = await get_runtime_for_user(flight_id, user_id=int(user.id))
    orch = await get_orchestrator()
    idempotency_key = resolve_idempotency_key(
        payload.idempotency_key,
        idempotency_key_header,
    )

    result = await apply_mission_command(
        orch=orch,
        runtime=runtime,
        command=command,
        idempotency_key=idempotency_key,
        requested_by_user_id=int(user.id),
        reason=payload.reason,
    )

    if result.accepted and command in {"abort", "rth", "land"} and result.state_before == "queued":
        active_task = getattr(orch, "_active_mission_task", None)
        if active_task is not None and not active_task.done():
            active_task.cancel()
            logger.info("Cancelled queued mission task for %s after abort command", flight_id)

    return result
