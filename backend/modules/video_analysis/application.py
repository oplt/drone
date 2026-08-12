from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import aiofiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.fields.service import field_service
from backend.modules.identity.models import User
from backend.modules.missions.repository import mission_runtime_repo
from backend.modules.video_analysis.model_storage import resolve_model_path
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.schemas import (
    CUSTOM_MODEL_PREFIX,
    AnalyzeVideoRequest,
    VideoDetectionOut,
)
from backend.modules.video_analysis.service.queue import VideoAnalysisQueue, VideoAnalysisQueueError
from backend.modules.vision_models.application import VisionApplication, VisionNotFound

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
        self,
        db: AsyncSession,
        *,
        video_id: str,
        request: AnalyzeVideoRequest,
        user: User,
        orchestration_key: str | None = None,
    ):
        repo = VideoAnalysisRepository(db)
        video = await repo.get_video_for_user(video_id, user)
        if video is None:
            raise VideoAnalysisNotFound("Video not found")
        if orchestration_key:
            existing = await repo.get_job_by_orchestration_key(orchestration_key)
            if existing is not None:
                if existing.video_id != video.id or existing.org_id != video.org_id:
                    raise VideoAnalysisConflict(
                        "Analysis idempotency key belongs to different input media."
                    )
                return existing
        model_name = request.model_name
        if request.model_version_id:
            try:
                _, version = await VisionApplication().resolve_registered_weights(
                    db,
                    request.model_version_id,
                    org_id=user.org_id,
                    user_id=user.id,
                    require_production=True,
                )
            except VisionNotFound as exc:
                raise VideoAnalysisModelUnavailable(str(exc)) from exc
            model_name = f"{version.model.name} v{version.version}"
        if request.model_version_id is None and (
            model_name.startswith(CUSTOM_MODEL_PREFIX)
            and not resolve_model_path(model_name).is_file()
        ):
            raise VideoAnalysisModelUnavailable(
                "Custom model is not installed. Add the selected .pt file under "
                "backend/storage/ml_models/ or select a built-in YOLO26 model."
            )
        try:
            job = await repo.create_job(
                video=video,
                model_name=model_name,
                model_version_id=request.model_version_id,
                small_object_mode=request.small_object_mode,
                tracking_enabled=request.tracking_enabled,
                tracker_type=request.tracker_type,
                frame_stride_seconds=request.frame_stride_seconds,
                confidence_threshold=request.confidence_threshold,
                orchestration_key=orchestration_key,
            )
        except IntegrityError:
            await db.rollback()
            existing = (
                await repo.get_job_by_orchestration_key(orchestration_key)
                if orchestration_key
                else None
            )
            if existing is None or existing.video_id != video.id:
                raise
            return existing
        try:
            self.queue.enqueue(job_id=job.id)
        except VideoAnalysisQueueError as exc:
            await repo.mark_job_failed(
                job,
                "Analysis worker unavailable.",
                video=video,
                reason_code="QUEUE_UNAVAILABLE",
                stage="queue",
            )
            raise VideoAnalysisConflict("Analysis worker unavailable. Retry shortly.") from exc
        return job

    async def get_job(self, db: AsyncSession, *, job_id: str, user: User):
        job = await VideoAnalysisRepository(db).get_job_for_user(job_id, user)
        if job is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        return job

    async def cancel_job(self, db: AsyncSession, *, job_id: str, user: User):
        job = await VideoAnalysisRepository(db).cancel_job(job_id, user=user)
        if job is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        return job

    async def list_detections(self, db: AsyncSession, *, job_id: str, user: User, limit: int):
        repo = VideoAnalysisRepository(db)
        if await repo.get_job_for_user(job_id, user) is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        return await repo.list_detections_for_user(job_id, user, limit=limit)

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[float, str] | None:
        if not cursor:
            return None
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            return float(value[0]), str(value[1])
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise VideoAnalysisConflict("Invalid detection cursor") from exc

    @staticmethod
    def _encode_cursor(timestamp: float, detection_id: str) -> str:
        payload = json.dumps([timestamp, detection_id], separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(payload).decode()

    async def page_detections(
        self,
        db: AsyncSession,
        *,
        job_id: str,
        user: User,
        limit: int,
        cursor: str | None,
        since_id: str | None,
    ) -> dict:
        repo = VideoAnalysisRepository(db)
        job = await repo.get_job_for_user(job_id, user)
        if job is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        rows, has_more, total = await repo.page_detections_for_user(
            job_id,
            user,
            limit=limit,
            after=self._decode_cursor(cursor),
            since_id=since_id,
        )
        last = rows[-1] if rows else None
        return {
            "items": rows,
            "next_cursor": (
                self._encode_cursor(last.timestamp_seconds, last.id)
                if has_more and last is not None
                else None
            ),
            "has_more": has_more,
            "job_version": job.attempt,
            "status": job.status,
            "total_estimate": total,
        }

    async def detection_aggregates(
        self,
        db: AsyncSession,
        *,
        job_id: str,
        user: User,
        bucket_seconds: float,
    ) -> dict:
        repo = VideoAnalysisRepository(db)
        if await repo.get_job_for_user(job_id, user) is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        return {
            "job_id": job_id,
            "bucket_seconds": bucket_seconds,
            "buckets": await repo.aggregate_detections(
                job_id, user, bucket_seconds=bucket_seconds
            ),
        }

    async def resolve_evidence(
        self, db: AsyncSession, *, detection_id: str, user: User
    ) -> dict:
        detection = await VideoAnalysisRepository(db).get_detection_for_user(
            detection_id, user
        )
        if detection is None:
            raise VideoAnalysisNotFound("Detection not found")
        output = VideoDetectionOut.model_validate(detection)
        return {
            "detection_id": detection.id,
            "evidence": output.evidence,
            "evidence_url": output.evidence_url,
            "evidence_path": None,
            "resolved_at": datetime.now(UTC),
        }

    async def resolve_evidence_content_path(
        self, db: AsyncSession, *, detection_id: str, user: User
    ) -> tuple[Path, str]:
        detection = await VideoAnalysisRepository(db).get_detection_for_user(
            detection_id, user
        )
        storage = detection.storage_object if detection is not None else None
        if storage is None or storage.state != "final":
            raise VideoAnalysisNotFound("Evidence is unavailable")
        path = Path(storage.backend_key)
        if not path.is_file():
            raise VideoAnalysisNotFound("Evidence is unavailable")
        return path, storage.mime

    async def get_summary(self, db: AsyncSession, *, job_id: str, user: User):
        repo = VideoAnalysisRepository(db)
        job = await repo.get_job_for_user(job_id, user)
        if job is None:
            raise VideoAnalysisNotFound("Analysis job not found")
        summary = await repo.summarize_detections(job_id, user)
        registered_model = None
        if job.model_version_id:
            try:
                _, version = await VisionApplication().resolve_registered_weights(
                    db,
                    job.model_version_id,
                    org_id=user.org_id,
                    user_id=user.id,
                    require_production=False,
                )
                registered_model = {
                    "name": version.model.name,
                    "version": version.version,
                    "crop": version.model.crop,
                    "task_type": version.model.task_type,
                    "classes": version.classes,
                }
            except VisionNotFound:
                registered_model = None
        return {
            "job_id": job.id,
            "frames_analyzed": job.frames_processed,
            **summary,
            "model_name": job.model_name,
            "model_version": job.model_version,
            "model_version_id": job.model_version_id,
            "registered_model": registered_model,
            "tracking_enabled": job.tracking_enabled,
            "tracker_type": job.tracker_type,
            "small_object_mode": job.small_object_mode,
            "frame_stride_seconds": job.frame_stride_seconds,
            "confidence_threshold": job.confidence_threshold,
        }

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
