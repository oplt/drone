from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_user_header_or_query
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
from backend.observability.instruments import observed_span

router = APIRouter(prefix="/video-analysis", tags=["video-analysis"])
application = VideoAnalysisApplication()


@router.get("/videos", response_model=list[VideoAssetOut])
async def list_videos(
    mission_id: str | None = Query(default=None),
    field_id: int | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[VideoAssetOut]:
    try:
        return await application.list_videos(
            db,
            user=org_user.user,
            mission_id=mission_id,
            field_id=field_id,
            limit=limit,
        )
    except VideoAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/videos/{video_id}/stream")
async def stream_video(
    video_id: str,
    db=Depends(get_db),
    user=Depends(require_user_header_or_query),
) -> FileResponse:
    try:
        path, content_type = await application.resolve_video_stream_path(
            db, video_id=video_id, user=user
        )
    except VideoAnalysisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type = content_type or "video/mp4"
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.post("/videos", response_model=VideoAssetOut)
async def upload_video(
    file: UploadFile = File(...),
    mission_id: str | None = Form(default=None),
    field_id: int | None = Form(default=None),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAssetOut:
    try:
        with observed_span("video.upload", mission_id=mission_id, camera_name="upload"):
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
        with observed_span(
            "video.analysis.start",
            camera_name="offline_video",
            **{"model.name": request.model_name},
        ):
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
