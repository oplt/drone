"""Tenant-scoped lifecycle stream for agriculture analysis runs."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.agriculture.lifecycle import ANALYSIS_EVENT_DOMAIN
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import common as _common
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.workflow_events.service import workflow_event_stream

router = APIRouter()


@router.get("/analysis-runs/{run_id}/events")
async def stream_analysis_run_events(
    run_id: str,
    request: Request,
    after_id: int = Query(0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: AsyncSession = Depends(get_db, scope="function"),
    org_user: OrgUser = Depends(require_org_user, scope="function"),
):
    run = await agriculture_repository.get_run(db, run_id=run_id, user=org_user.user)
    if run is None:
        raise HTTPException(status_code=404, detail="Agriculture analysis run not found")
    flight = await _common._owned_flight(run.flight_id, org_user, db)
    cursor = after_id
    if last_event_id:
        try:
            cursor = max(cursor, int(last_event_id))
        except ValueError:
            pass
    return StreamingResponse(
        workflow_event_stream(
            request,
            domain=ANALYSIS_EVENT_DOMAIN,
            stream_id=run.id,
            org_id=flight.org_id,
            user_id=int(org_user.user.id),
            after_id=cursor,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
