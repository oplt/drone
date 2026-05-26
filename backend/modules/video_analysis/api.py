from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.video_analysis.application import (
    VideoAnalysisApplication,
    VideoAnalysisConflict,
    VideoAnalysisModelUnavailable,
    VideoAnalysisNotFound,
    VideoAnalysisUploadError,
)
from backend.modules.video_analysis.schemas import (
    AnalyzeVideoRequest,
    VideoAnalysisJobOut,
    VideoAssetOut,
    VideoDetectionOut,
)

router = APIRouter(prefix="/video-analysis", tags=["video-analysis"])
application = VideoAnalysisApplication()


@router.post("/videos", response_model=VideoAssetOut)
async def upload_video(
    file: UploadFile = File(...),
    mission_id: str | None = Form(default=None),
    field_id: int | None = Form(default=None),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAssetOut:
    try:
        return await application.upload_video(
            db,
            file=file,
            mission_id=mission_id,
            field_id=field_id,
            user=org_user.user,
        )
    except VideoAnalysisUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VideoAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/videos/{video_id}/analyze", response_model=VideoAnalysisJobOut)
async def analyze_video(
    video_id: str,
    request: AnalyzeVideoRequest,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAnalysisJobOut:
    try:
        return await application.start_analysis(
            db, video_id=video_id, request=request, user=org_user.user
        )
    except VideoAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VideoAnalysisModelUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VideoAnalysisConflict as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/jobs/{job_id}", response_model=VideoAnalysisJobOut)
async def get_job(
    job_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAnalysisJobOut:
    try:
        return await application.get_job(db, job_id=job_id, user=org_user.user)
    except VideoAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/detections", response_model=list[VideoDetectionOut])
async def list_detections(
    job_id: str,
    limit: int = Query(500, ge=1, le=2000),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[VideoDetectionOut]:
    try:
        return await application.list_detections(db, job_id=job_id, user=org_user.user, limit=limit)
    except VideoAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
