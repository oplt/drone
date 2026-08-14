from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.core.errors.public import public_error
from backend.modules.identity.dependencies import require_user
from backend.modules.missions.api.mission_route_schemas import (
    MissionCreateIn,
    PreflightRunOut,
)
from backend.modules.missions.api.preflight_store import (
    get_preflight_run_record,
    preflight_record_out,
    run_preflight_report,
    store_preflight_run,
)
from backend.modules.missions.service.mission_builder import build_mission
from backend.modules.missions.service.mission_start import mission_fingerprint
from backend.modules.vehicle_runtime.factory import get_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])


@router.post("/preflight/run", response_model=PreflightRunOut)
async def run_preflight(
    payload: MissionCreateIn,
    user=Depends(require_user),
):
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
        report = await run_preflight_report(
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

    rec = await store_preflight_run(
        user_id=int(user.id),
        mission_fingerprint=mission_fingerprint(payload),
        report=report,
    )
    return preflight_record_out(rec)


@router.get("/preflight/runs/{preflight_run_id}", response_model=PreflightRunOut)
async def get_preflight_run(
    preflight_run_id: str,
    user=Depends(require_user),
):
    rec = await get_preflight_run_record(preflight_run_id)
    if rec is None or rec.user_id != int(user.id):
        raise HTTPException(status_code=404, detail="Preflight run not found")
    return preflight_record_out(rec)
