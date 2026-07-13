from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity.models import User
from backend.modules.video_analysis.models import VideoAnalysisJob, VideoAsset, VideoDetection


class VideoAnalysisRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_video(
        self,
        *,
        original_filename: str,
        storage_path: str,
        content_type: str | None = None,
        mission_id: str | None = None,
        field_id: int | None = None,
        org_id: int | None = None,
        uploaded_by_user_id: int | None = None,
        status: str = "uploaded",
    ) -> VideoAsset:
        video = VideoAsset(
            original_filename=original_filename,
            storage_path=storage_path,
            content_type=content_type,
            mission_id=mission_id,
            field_id=field_id,
            org_id=org_id,
            uploaded_by_user_id=uploaded_by_user_id,
            status=status,
        )
        self.db.add(video)
        await self.db.commit()
        await self.db.refresh(video)
        return video

    def _visible_video(self, user: User):
        if user.org_id is not None:
            return VideoAsset.org_id == user.org_id
        return VideoAsset.uploaded_by_user_id == user.id

    async def get_video_for_user(self, video_id: str, user: User) -> VideoAsset | None:
        result = await self.db.execute(
            select(VideoAsset).where(VideoAsset.id == video_id, self._visible_video(user))
        )
        return result.scalar_one_or_none()

    async def get_video(self, video_id: str) -> VideoAsset | None:
        return await self.db.get(VideoAsset, video_id)

    async def get_video_by_storage_path(self, storage_path: str) -> VideoAsset | None:
        result = await self.db.execute(
            select(VideoAsset).where(VideoAsset.storage_path == storage_path)
        )
        return result.scalar_one_or_none()

    async def attach_video_to_mission(
        self,
        video: VideoAsset,
        *,
        mission_id: str,
        field_id: int | None = None,
    ) -> VideoAsset:
        video.mission_id = mission_id
        if field_id is not None:
            video.field_id = field_id
        if video.status == "uploaded":
            video.status = "mission_recording"
        await self.db.commit()
        await self.db.refresh(video)
        return video

    async def list_videos_for_user(
        self,
        user: User,
        *,
        mission_id: str | None = None,
        field_id: int | None = None,
        limit: int = 20,
    ) -> list[VideoAsset]:
        stmt = select(VideoAsset).where(self._visible_video(user))
        if mission_id:
            stmt = stmt.where(VideoAsset.mission_id == mission_id)
        if field_id is not None:
            stmt = stmt.where(VideoAsset.field_id == field_id)
        stmt = stmt.order_by(VideoAsset.created_at.desc()).limit(max(1, int(limit)))
        return list((await self.db.scalars(stmt)).all())

    async def update_video_metadata(
        self,
        video: VideoAsset,
        *,
        fps: float | None,
        width: int | None,
        height: int | None,
        duration_seconds: float | None,
        status: str | None = None,
    ) -> VideoAsset:
        video.fps = fps
        video.width = width
        video.height = height
        video.duration_seconds = duration_seconds
        if status:
            video.status = status
        await self.db.commit()
        await self.db.refresh(video)
        return video

    async def create_job(
        self,
        *,
        video: VideoAsset,
        model_name: str,
        frame_stride_seconds: float,
        confidence_threshold: float,
    ) -> VideoAnalysisJob:
        job = VideoAnalysisJob(
            video_id=video.id,
            mission_id=video.mission_id,
            org_id=video.org_id,
            model_name=model_name,
            frame_stride_seconds=frame_stride_seconds,
            confidence_threshold=confidence_threshold,
            status="queued",
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_job(self, job_id: str) -> VideoAnalysisJob | None:
        return await self.db.get(VideoAnalysisJob, job_id)

    async def get_job_for_user(self, job_id: str, user: User) -> VideoAnalysisJob | None:
        result = await self.db.execute(
            select(VideoAnalysisJob)
            .join(VideoAsset, VideoAsset.id == VideoAnalysisJob.video_id)
            .where(VideoAnalysisJob.id == job_id, self._visible_video(user))
        )
        return result.scalar_one_or_none()

    async def mark_job_running(self, job: VideoAnalysisJob) -> None:
        await self.db.execute(delete(VideoDetection).where(VideoDetection.job_id == job.id))
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.finished_at = None
        job.error = None
        job.progress = 0.0
        job.source_checksum = None
        job.frames_received = 0
        job.frames_processed = 0
        job.frames_dropped = 0
        job.frames_failed = 0
        job.total_inference_latency_ms = 0.0
        await self.db.commit()

    async def set_model_version(self, job: VideoAnalysisJob, version: str) -> None:
        job.model_version = version[:160]
        await self.db.commit()

    async def set_source_checksum(self, job: VideoAnalysisJob, checksum: str) -> None:
        job.source_checksum = checksum[:64]
        await self.db.commit()

    async def update_processing_metrics(
        self,
        job: VideoAnalysisJob,
        *,
        frames_received: int,
        frames_processed: int,
        frames_dropped: int,
        frames_failed: int,
        total_inference_latency_ms: float,
    ) -> None:
        job.frames_received = max(0, int(frames_received))
        job.frames_processed = max(0, int(frames_processed))
        job.frames_dropped = max(0, int(frames_dropped))
        job.frames_failed = max(0, int(frames_failed))
        job.total_inference_latency_ms = max(0.0, float(total_inference_latency_ms))
        await self.db.commit()

    async def mark_job_failed(self, job: VideoAnalysisJob, error: str) -> None:
        job.status = "failed"
        job.error = error[:4000]
        job.finished_at = datetime.now(UTC)
        await self.db.commit()

    async def mark_job_completed(self, job: VideoAnalysisJob) -> None:
        job.status = "completed"
        job.progress = 100.0
        job.finished_at = datetime.now(UTC)
        await self.db.commit()

    async def flush_batch(
        self,
        detections: list[VideoDetection],
        *,
        job: VideoAnalysisJob | None = None,
        progress: float | None = None,
    ) -> None:
        self.db.add_all(detections)
        if job is not None and progress is not None:
            job.progress = max(0.0, min(100.0, progress))
        await self.db.commit()

    async def set_video_status(self, video: VideoAsset, status: str) -> None:
        video.status = status
        await self.db.commit()

    async def list_detections_for_user(
        self, job_id: str, user: User, limit: int = 500
    ) -> list[VideoDetection]:
        stmt = (
            select(VideoDetection)
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.job_id == job_id)
            .where(self._visible_video(user))
            .order_by(VideoDetection.timestamp_seconds.asc())
            .limit(limit)
        )
        return list((await self.db.scalars(stmt)).all())
