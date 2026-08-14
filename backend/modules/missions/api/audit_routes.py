from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.missions.api.mission_route_schemas import FlightEventOut, MissionPreflightOut
from backend.modules.missions.application import mission_application

router = APIRouter(tags=["tasks"])


@router.get("/missions/{flight_id}/preflight", response_model=MissionPreflightOut)
async def get_mission_preflight(
    flight_id: str,
    user=Depends(require_user),
):
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
            id=event.id,
            type=event.type,
            data=event.data or {},
            created_at=event.created_at.timestamp() if event.created_at else 0.0,
        )
        for event in events
    ]
    return page_from_offset(items, limit=page_limit, offset=page_offset)
