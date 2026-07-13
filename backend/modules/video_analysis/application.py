from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import uuid4

import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.fields.service import field_service
from backend.modules.identity.models import User
from backend.modules.missions.repository import mission_runtime_repo
from backend.modules.video_analysis.model_storage import resolve_model_path
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.schemas import CUSTOM_MODEL_PREFIX, AnalyzeVideoRequest
from backend.modules.video_analysis.service.queue import VideoAnalysisQueue, VideoAnalysisQueueError

UPLOAD_ROOT = Path(settings.video_analysis_upload_dir)
MAX_UPLOAD_BYTES = settings.video_analysis_max_upload_bytes
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class UploadedVideo(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


class VideoAnalysisNotFound(RuntimeError):
    pass


class VideoAnalysisConflict(RuntimeError):
    pass


class VideoAnalysisUploadError(ValueError):
    pass


class VideoAnalysisModelUnavailable(ValueError):
    pass


class VideoAnalysisApplication:
    def __init__(self, queue: VideoAnalysisQueue | None = None) -> None:
        self.queue = queue or VideoAnalysisQueue()

    async def upload_video(
        self,
        db: AsyncSession,
        *,
        file: UploadedVideo,
        mission_id: str | None,
        field_id: int | None,
        user: User,
    ):
        safe_name = Path(file.filename or "video.mp4").name
        if Path(safe_name).suffix.lower() not in VIDEO_SUFFIXES:
            raise VideoAnalysisUploadError("Supported video formats: MP4, MOV, AVI, MKV, WEBM.")
        if not file.content_type or not file.content_type.startswith("video/"):
            raise VideoAnalysisUploadError("Upload must be a video file.")
        if (
            field_id is not None
            and await field_service.get_owned(db, field_id=field_id, user=user) is None
        ):
            raise VideoAnalysisNotFound("Field not found")
        if (
            mission_id is not None
            and await mission_runtime_repo.get_by_client_id_for_user(mission_id, user.id) is None
        ):
            raise VideoAnalysisNotFound("Mission not found")

        await run_blocking(
            UPLOAD_ROOT.mkdir,
            parents=True,
            exist_ok=True,
            boundary="filesystem",
            operation="video_upload_directory",
            timeout_s=30.0,
        )
        storage_path = UPLOAD_ROOT / f"{uuid4()}_{safe_name}"
        size = 0
        try:
            async with aiofiles.open(storage_path, "wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise VideoAnalysisUploadError("Video exceeds 1 GB upload limit.")
                    await output.write(chunk)
        except Exception:
            await run_blocking(
                storage_path.unlink,
                missing_ok=True,
                boundary="filesystem",
                operation="video_upload_cleanup",
                timeout_s=30.0,
            )
            raise
        finally:
            await file.close()

        try:
            return await VideoAnalysisRepository(db).create_video(
                original_filename=safe_name,
                storage_path=str(storage_path),
                content_type=file.content_type,
                mission_id=mission_id,
                field_id=field_id,
                org_id=user.org_id,
                uploaded_by_user_id=user.id,
            )
        except Exception:
            await run_blocking(
                storage_path.unlink,
                missing_ok=True,
                boundary="filesystem",
                operation="video_upload_repository_cleanup",
                timeout_s=30.0,
            )
            raise

    async def start_analysis(
        self, db: AsyncSession, *, video_id: str, request: AnalyzeVideoRequest, user: User
    ):
        repo = VideoAnalysisRepository(db)
        video = await repo.get_video_for_user(video_id, user)
        if video is None:
            raise VideoAnalysisNotFound("Video not found")
        if (
            request.model_name.startswith(CUSTOM_MODEL_PREFIX)
            and not resolve_model_path(request.model_name).is_file()
        ):
            raise VideoAnalysisModelUnavailable(
                "Custom model is not installed. Add the selected .pt file under "
                "backend/storage/ml_models/ or select a built-in YOLO26 model."
            )
        job = await repo.create_job(
            video=video,
            model_name=request.model_name,
            frame_stride_seconds=request.frame_stride_seconds,
            confidence_threshold=request.confidence_threshold,
        )
        try:
            self.queue.enqueue(job_id=job.id)
        except VideoAnalysisQueueError as exc:
            await repo.mark_job_failed(job, "Analysis worker unavailable.")
            raise VideoAnalysisConflict("Analysis worker unavailable. Retry shortly.") from exc
        return job

    async def get_job(self, db: AsyncSession, *, job_id: str, user: User):
        job = await VideoAnalysisRepository(db).get_job_for_user(job_id, user)
        if job is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        return job

    async def list_detections(self, db: AsyncSession, *, job_id: str, user: User, limit: int):
        repo = VideoAnalysisRepository(db)
        if await repo.get_job_for_user(job_id, user) is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        return await repo.list_detections_for_user(job_id, user, limit=limit)

    async def list_videos(
        self,
        db: AsyncSession,
        *,
        user: User,
        mission_id: str | None = None,
        field_id: int | None = None,
        limit: int = 20,
    ):
        if (
            field_id is not None
            and await field_service.get_owned(db, field_id=field_id, user=user) is None
        ):
            raise VideoAnalysisNotFound("Field not found")
        return await VideoAnalysisRepository(db).list_videos_for_user(
            user,
            mission_id=mission_id,
            field_id=field_id,
            limit=limit,
        )

    async def resolve_video_stream_path(
        self, db: AsyncSession, *, video_id: str, user: User
    ) -> tuple[Path, str | None]:
        video = await VideoAnalysisRepository(db).get_video_for_user(video_id, user)
        if video is None:
            raise VideoAnalysisNotFound("Video not found")
        path = Path(video.storage_path)
        if not path.is_file():
            raise VideoAnalysisNotFound("Video file is not available on disk")
        return path, video.content_type
