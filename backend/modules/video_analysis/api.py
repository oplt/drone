from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from backend.core.api_errors import map_domain_exception
from backend.core.database.session import get_db
from backend.core.config.runtime import settings
from backend.core.rate_limit import enforce_rate_limit
from backend.modules.identity.dependencies import (
    OrgUser,
    require_org_user,
    require_user,
)
from backend.modules.video_analysis.application import (
    VideoAnalysisApplication,
    VideoAnalysisConflict,
    VideoAnalysisModelUnavailable,
    VideoAnalysisNotFound,
    VideoAnalysisUploadError,
)
from backend.modules.video_analysis.evidence import EvidenceResolverOut
from backend.modules.video_analysis.schemas import (
    AnalyzeVideoRequest,
    VideoAnalysisJobOut,
    VideoAnalysisSummaryOut,
    VideoAssetOut,
    VideoCaptureMetadataPatch,
    VideoDetectionAggregateOut,
    VideoDetectionPageOut,
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
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.patch("/videos/{video_id}/capture-metadata", response_model=VideoAssetOut)
async def patch_capture_metadata(
    video_id: str,
    request: VideoCaptureMetadataPatch,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAssetOut:
    try:
        return await application.update_capture_metadata(
            db,
            video_id=video_id,
            user=org_user.user,
            patch=request,
        )
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.get("/videos/{video_id}/stream")
async def stream_video(
    video_id: str,
    db=Depends(get_db),
    user=Depends(require_user),
) -> FileResponse:
    try:
        path, content_type = await application.resolve_video_stream_path(
            db, video_id=video_id, user=user
        )
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc
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
    await enforce_rate_limit(
        key=f"video-analysis:upload:{org_user.user.id}",
        limit=settings.video_analysis_rate_uploads_per_window,
        window_seconds=settings.api_rate_window_seconds,
    )
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
        raise map_domain_exception(exc, domain="video_analysis") from exc
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.post("/videos/{video_id}/analyze", response_model=VideoAnalysisJobOut)
async def analyze_video(
    video_id: str,
    request: AnalyzeVideoRequest,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAnalysisJobOut:
    await enforce_rate_limit(
        key=f"video-analysis:analyze:{org_user.user.id}",
        limit=settings.video_analysis_rate_analyze_starts_per_window,
        window_seconds=settings.api_rate_window_seconds,
    )
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
        raise map_domain_exception(exc, domain="video_analysis") from exc
    except VideoAnalysisModelUnavailable as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc
    except VideoAnalysisConflict as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.get("/jobs/{job_id}", response_model=VideoAnalysisJobOut)
async def get_job(
    job_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAnalysisJobOut:
    try:
        return await application.get_job(db, job_id=job_id, user=org_user.user)
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.post("/jobs/{job_id}/cancel", response_model=VideoAnalysisJobOut)
async def cancel_job(
    job_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAnalysisJobOut:
    try:
        return await application.cancel_job(db, job_id=job_id, user=org_user.user)
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.get("/jobs/{job_id}/detections", response_model=VideoDetectionPageOut)
async def list_detections(
    job_id: str,
    cursor: str | None = Query(default=None),
    since_id: str | None = Query(default=None),
    limit: int = Query(250, ge=1, le=500),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    label: str | None = Query(default=None, min_length=1, max_length=128),
    since_ts: float | None = Query(default=None, ge=0.0),
    until_ts: float | None = Query(default=None, ge=0.0),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoDetectionPageOut:
    try:
        return await application.page_detections(
            db,
            job_id=job_id,
            user=org_user.user,
            limit=limit,
            cursor=cursor,
            since_id=since_id,
            min_confidence=min_confidence,
            label=label,
            since_ts=since_ts,
            until_ts=until_ts,
        )
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc
    except VideoAnalysisConflict as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.get(
    "/jobs/{job_id}/detections/aggregate",
    response_model=VideoDetectionAggregateOut,
)
async def aggregate_detections(
    job_id: str,
    bucket_seconds: float = Query(10.0, ge=0.5, le=3600.0),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    label: str | None = Query(default=None, min_length=1, max_length=128),
    since_ts: float | None = Query(default=None, ge=0.0),
    until_ts: float | None = Query(default=None, ge=0.0),
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoDetectionAggregateOut:
    try:
        return await application.detection_aggregates(
            db,
            job_id=job_id,
            user=org_user.user,
            bucket_seconds=bucket_seconds,
            min_confidence=min_confidence,
            label=label,
            since_ts=since_ts,
            until_ts=until_ts,
        )
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.get("/evidence/{detection_id}", response_model=EvidenceResolverOut)
async def resolve_evidence(
    detection_id: str,
    db=Depends(get_db),
    user=Depends(require_user),
) -> EvidenceResolverOut:
    try:
        return await application.resolve_evidence(
            db, detection_id=detection_id, user=user
        )
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc


@router.get("/evidence/{detection_id}/content")
async def stream_evidence(
    detection_id: str,
    db=Depends(get_db),
    user=Depends(require_user),
) -> FileResponse:
    try:
        path, media_type = await application.resolve_evidence_content_path(
            db, detection_id=detection_id, user=user
        )
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc
    return FileResponse(path, media_type=media_type)


@router.get("/jobs/{job_id}/summary", response_model=VideoAnalysisSummaryOut)
async def get_analysis_summary(
    job_id: str,
    db=Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> VideoAnalysisSummaryOut:
    try:
        return await application.get_summary(db, job_id=job_id, user=org_user.user)
    except VideoAnalysisNotFound as exc:
        raise map_domain_exception(exc, domain="video_analysis") from exc
