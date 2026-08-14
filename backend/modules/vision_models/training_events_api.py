"""Tenant-scoped lifecycle stream for vision training projects."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.vision_models.lifecycle import TRAINING_EVENT_DOMAIN
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.workflow_events.service import workflow_event_stream

router = APIRouter()


@router.get("/projects/{project_id}/training-events")
async def stream_training_events(
    project_id: str,
    request: Request,
    after_id: int = Query(0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db=Depends(get_db, scope="function"),
    org_user: OrgUser = Depends(require_org_user, scope="function"),
):
    project = await VisionRepository(db).get_project(project_id, org_user.user)
    if project is None:
        raise HTTPException(status_code=404, detail="Vision project not found")
    cursor = after_id
    if last_event_id:
        try:
            cursor = max(cursor, int(last_event_id))
        except ValueError:
            pass
    return StreamingResponse(
        workflow_event_stream(
            request,
            domain=TRAINING_EVENT_DOMAIN,
            stream_id=project.id,
            org_id=project.org_id,
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
