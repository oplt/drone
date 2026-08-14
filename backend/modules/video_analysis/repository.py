from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, cast, delete, distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

from backend.core.authz.visibility import org_or_owner_visibility, org_scoped_visibility
from backend.core.config.runtime import settings
from backend.shared.storage_objects import reconcile_staged_storage_objects
from backend.modules.identity.models import User
from backend.modules.video_analysis.models import (
    StorageObject,
    VideoAnalysisJob,
    VideoAsset,
    VideoDetection,
)


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

    def _visible_video(self, user: User) -> ColumnElement[bool]:
        return org_or_owner_visibility(
            org_column=VideoAsset.org_id,
            owner_column=VideoAsset.uploaded_by_user_id,
            user_org_id=user.org_id,
            user_id=user.id,
        )

    def _visible_detection(self, org_id: int | None) -> ColumnElement[bool]:
        return org_scoped_visibility(
            org_column=VideoDetection.org_id,
            user_org_id=org_id,
        )

    @staticmethod
    def _apply_detection_filters(
        stmt: Select,
        *,
        min_confidence: float | None = None,
        label: str | None = None,
        since_ts: float | None = None,
        until_ts: float | None = None,
        min_lon: float | None = None,
        min_lat: float | None = None,
        max_lon: float | None = None,
        max_lat: float | None = None,
    ) -> Select:
        if min_confidence is not None:
            stmt = stmt.where(VideoDetection.confidence >= min_confidence)
        if label is not None:
            stmt = stmt.where(VideoDetection.label == label)
        if since_ts is not None:
            stmt = stmt.where(VideoDetection.timestamp_seconds >= since_ts)
        if until_ts is not None:
            stmt = stmt.where(VideoDetection.timestamp_seconds <= until_ts)
        if any(value is not None for value in (min_lon, min_lat, max_lon, max_lat)):
            stmt = stmt.where(
                VideoDetection.lon.is_not(None),
                VideoDetection.lat.is_not(None),
            )
            if min_lon is not None:
                stmt = stmt.where(VideoDetection.lon >= min_lon)
            if min_lat is not None:
                stmt = stmt.where(VideoDetection.lat >= min_lat)
            if max_lon is not None:
                stmt = stmt.where(VideoDetection.lon <= max_lon)
            if max_lat is not None:
                stmt = stmt.where(VideoDetection.lat <= max_lat)
        return stmt

    async def get_video_for_user(self, video_id: str, user: User) -> VideoAsset | None:
        result = await self.db.execute(
            select(VideoAsset).where(VideoAsset.id == video_id, self._visible_video(user))
        )
        return result.scalar_one_or_none()

    async def video_has_analyzed_jobs(self, video_id: str) -> bool:
        count = await self.db.scalar(
            select(func.count())
            .select_from(VideoAnalysisJob)
            .where(
                VideoAnalysisJob.video_id == video_id,
                VideoAnalysisJob.status.in_(("completed", "failed", "running", "queued")),
            )
        )
        return int(count or 0) > 0

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

    async def list_videos_for_scope(
        self,
        *,
        mission_id: str,
        org_id: int | None,
        user_id: int | None,
    ) -> list[VideoAsset]:
        stmt = select(VideoAsset).where(VideoAsset.mission_id == mission_id)
        stmt = stmt.where(
            org_or_owner_visibility(
                org_column=VideoAsset.org_id,
                owner_column=VideoAsset.uploaded_by_user_id,
                user_org_id=org_id,
                user_id=user_id or 0,
            )
        )
        return list((await self.db.scalars(stmt.order_by(VideoAsset.created_at))).all())

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
        model_version_id: str | None = None,
        small_object_mode: bool = False,
        tracking_enabled: bool = False,
        tracker_type: str = "bytetrack",
        orchestration_key: str | None = None,
    ) -> VideoAnalysisJob:
        job = VideoAnalysisJob(
            video_id=video.id,
            mission_id=video.mission_id,
            org_id=video.org_id,
            model_name=model_name,
            model_version_id=model_version_id,
            small_object_mode=small_object_mode,
            tracking_enabled=tracking_enabled,
            tracker_type=tracker_type,
            orchestration_key=orchestration_key,
            frame_stride_seconds=frame_stride_seconds,
            confidence_threshold=confidence_threshold,
            capture_metadata_revision=video.capture_metadata_revision,
            status="queued",
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_job_by_orchestration_key(
        self, orchestration_key: str
    ) -> VideoAnalysisJob | None:
        return await self.db.scalar(
            select(VideoAnalysisJob).where(
                VideoAnalysisJob.orchestration_key == orchestration_key
            )
        )

    async def get_job(self, job_id: str) -> VideoAnalysisJob | None:
        return await self.db.get(VideoAnalysisJob, job_id)

    async def get_job_for_user(self, job_id: str, user: User) -> VideoAnalysisJob | None:
        result = await self.db.execute(
            select(VideoAnalysisJob)
            .join(VideoAsset, VideoAsset.id == VideoAnalysisJob.video_id)
            .where(VideoAnalysisJob.id == job_id, self._visible_video(user))
        )
        return result.scalar_one_or_none()

    async def mark_job_running(self, job: VideoAnalysisJob) -> int | None:
        now = datetime.now(UTC)
        current = await self.db.scalar(
            select(VideoAnalysisJob)
            .where(VideoAnalysisJob.id == job.id)
            .with_for_update()
        )
        if current is None:
            return None
        if current.status in {"completed", "cancelled"}:
            await self.db.rollback()
            return None
        if (
            current.status == "running"
            and current.lease_expires_at is not None
            and current.lease_expires_at > now
        ):
            await self.db.rollback()
            return None
        await self.db.execute(delete(VideoDetection).where(VideoDetection.job_id == job.id))
        current.status = "running"
        current.started_at = now
        current.finished_at = None
        current.error = None
        current.progress = 0.0
        current.source_checksum = None
        current.frames_received = 0
        current.frames_decoded = 0
        current.frames_attempted = 0
        current.frames_processed = 0
        current.frames_persisted = 0
        current.frames_dropped = 0
        current.frames_failed = 0
        current.total_inference_latency_ms = 0.0
        current.stage_timings = {}
        current.attempt += 1
        current.heartbeat_at = now
        current.lease_expires_at = now + timedelta(
            seconds=settings.video_analysis_job_lease_seconds
        )
        current.terminal_reason_code = None
        current.terminal_stage = None
        await self.db.commit()
        return int(current.attempt)

    async def heartbeat(
        self, job: VideoAnalysisJob, *, expected_attempt: int
    ) -> bool:
        if job.status != "running":
            return False
        now = datetime.now(UTC)
        if (
            job.heartbeat_at is not None
            and job.heartbeat_at
            > now - timedelta(seconds=settings.video_analysis_heartbeat_interval_seconds)
        ):
            return True
        result = await self.db.execute(
            update(VideoAnalysisJob)
            .where(
                VideoAnalysisJob.id == job.id,
                VideoAnalysisJob.status == "running",
                VideoAnalysisJob.attempt == expected_attempt,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now
                + timedelta(seconds=settings.video_analysis_job_lease_seconds),
            )
        )
        await self.db.commit()
        if result.rowcount == 1:
            set_committed_value(job, "heartbeat_at", now)
            return True
        return False

    async def set_model_version(self, job: VideoAnalysisJob, version: str) -> None:
        job.model_version = version[:160]
        await self.db.commit()

    async def set_loaded_model_hash(
        self, job: VideoAnalysisJob, loaded_model_hash: str
    ) -> None:
        job.loaded_model_hash = loaded_model_hash[:64]
        await self.db.commit()

    async def set_source_checksum(self, job: VideoAnalysisJob, checksum: str) -> None:
        job.source_checksum = checksum[:64]
        await self.db.commit()

    async def set_stage_timings(
        self, job: VideoAnalysisJob, timings: dict[str, float]
    ) -> None:
        job.stage_timings = {
            key: round(max(0.0, float(value)), 3) for key, value in timings.items()
        }
        await self.db.commit()

    async def update_processing_metrics(
        self,
        job: VideoAnalysisJob,
        *,
        frames_received: int,
        frames_decoded: int,
        frames_attempted: int,
        frames_processed: int,
        frames_persisted: int,
        frames_dropped: int,
        frames_failed: int,
        total_inference_latency_ms: float,
        expected_attempt: int,
    ) -> bool:
        result = await self.db.execute(
            update(VideoAnalysisJob)
            .where(
                VideoAnalysisJob.id == job.id,
                VideoAnalysisJob.status == "running",
                VideoAnalysisJob.attempt == expected_attempt,
            )
            .values(
                frames_received=max(0, int(frames_received)),
                frames_decoded=max(0, int(frames_decoded)),
                frames_attempted=max(0, int(frames_attempted)),
                frames_processed=max(0, int(frames_processed)),
                frames_persisted=max(0, int(frames_persisted)),
                frames_dropped=max(0, int(frames_dropped)),
                frames_failed=max(0, int(frames_failed)),
                total_inference_latency_ms=max(
                    0.0, float(total_inference_latency_ms)
                ),
            )
        )
        await self.db.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def mark_job_failed(
        self,
        job: VideoAnalysisJob,
        error: str,
        *,
        video: VideoAsset | None = None,
        reason_code: str = "INFERENCE_FAILED",
        stage: str = "inference",
        expected_attempt: int | None = None,
    ) -> bool:
        current = await self.db.scalar(
            select(VideoAnalysisJob)
            .where(VideoAnalysisJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            current is None
            or current.status in {"completed", "cancelled"}
            or (expected_attempt is not None and current.attempt != expected_attempt)
        ):
            await self.db.rollback()
            return False
        current.status = "failed"
        current.error = error[:4000]
        current.finished_at = datetime.now(UTC)
        current.heartbeat_at = None
        current.lease_expires_at = None
        current.terminal_reason_code = reason_code[:64]
        current.terminal_stage = stage[:64]
        if video is not None:
            video.status = "analysis_failed"
        await self.db.commit()
        return True

    async def mark_job_completed(
        self,
        job: VideoAnalysisJob,
        *,
        video: VideoAsset | None = None,
        expected_attempt: int | None = None,
    ) -> bool:
        current = await self.db.scalar(
            select(VideoAnalysisJob)
            .where(VideoAnalysisJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            current is None
            or current.status != "running"
            or (expected_attempt is not None and current.attempt != expected_attempt)
        ):
            await self.db.rollback()
            return False
        current.status = "completed"
        current.progress = 100.0
        current.finished_at = datetime.now(UTC)
        current.heartbeat_at = None
        current.lease_expires_at = None
        current.terminal_reason_code = "COMPLETED"
        current.terminal_stage = "completed"
        current_video = None
        if video is not None:
            current_video = await self.db.scalar(
                select(VideoAsset)
                .where(VideoAsset.id == current.video_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        if current_video is not None:
            current_video.status = "analyzed"
            if (
                current.capture_metadata_revision
                >= current_video.capture_metadata_revision
            ):
                current_video.reanalysis_required = False
        await self.db.commit()
        return True

    async def cancel_job(self, job_id: str, *, user: User) -> VideoAnalysisJob | None:
        job = await self.db.scalar(
            select(VideoAnalysisJob)
            .join(VideoAsset, VideoAsset.id == VideoAnalysisJob.video_id)
            .where(VideoAnalysisJob.id == job_id, self._visible_video(user))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None:
            await self.db.rollback()
            return None
        if job.status in {"completed", "failed", "cancelled"}:
            await self.db.commit()
            return job
        video = await self.db.get(VideoAsset, job.video_id)
        job.status = "cancelled"
        job.error = "Cancelled by user."
        job.finished_at = datetime.now(UTC)
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.terminal_reason_code = "USER_CANCELLED"
        job.terminal_stage = "cancelled"
        if video is not None:
            video.status = "analysis_cancelled"
        await self.db.execute(
            delete(VideoDetection).where(VideoDetection.job_id == job.id)
        )
        await self.db.commit()
        return job

    async def is_job_cancelled(self, job_id: str) -> bool:
        status: str | None = await self.db.scalar(
            select(VideoAnalysisJob.status).where(VideoAnalysisJob.id == job_id)
        )
        return status == "cancelled"

    async def cleanup_cancelled_job(self, job_id: str) -> None:
        job = await self.db.scalar(
            select(VideoAnalysisJob)
            .where(VideoAnalysisJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None or job.status != "cancelled":
            await self.db.rollback()
            return
        await self.db.execute(
            delete(VideoDetection).where(VideoDetection.job_id == job.id)
        )
        video = await self.db.get(VideoAsset, job.video_id)
        if video is not None:
            video.status = "analysis_cancelled"
        await self.db.commit()

    async def flush_batch(
        self,
        detections: list[VideoDetection],
        *,
        job: VideoAnalysisJob | None = None,
        progress: float | None = None,
        expected_attempt: int | None = None,
    ) -> bool:
        for detection in detections:
            if detection.storage_object is not None:
                detection.storage_object.state = "staged"
        self.db.add_all(detections)
        if job is not None and progress is not None:
            now = datetime.now(UTC)
            values: dict[str, object] = {
                "progress": max(0.0, min(100.0, progress))
            }
            if job.heartbeat_at is None or job.heartbeat_at <= now - timedelta(
                seconds=settings.video_analysis_heartbeat_interval_seconds
            ):
                values.update(
                    heartbeat_at=now,
                    lease_expires_at=now
                    + timedelta(seconds=settings.video_analysis_job_lease_seconds),
                )
            stmt = update(VideoAnalysisJob).where(
                VideoAnalysisJob.id == job.id,
                VideoAnalysisJob.status == "running",
            )
            if expected_attempt is not None:
                stmt = stmt.where(VideoAnalysisJob.attempt == expected_attempt)
            result = await self.db.execute(stmt.values(**values))
            if result.rowcount != 1:
                await self.db.rollback()
                return False
        await self.db.commit()
        storage_ids = [
            detection.storage_object_id
            for detection in detections
            if detection.storage_object_id
        ]
        if storage_ids:
            await self.db.execute(
                update(StorageObject)
                .where(StorageObject.id.in_(storage_ids), StorageObject.state == "staged")
                .values(state="final")
            )
            await self.db.commit()
        return True

    async def set_video_status(self, video: VideoAsset, status: str) -> None:
        video.status = status
        await self.db.commit()

    async def reconcile_stale_jobs(self, *, limit: int = 100) -> int:
        now = datetime.now(UTC)
        jobs = list(
            (
                await self.db.scalars(
                    select(VideoAnalysisJob)
                    .where(
                        VideoAnalysisJob.status == "running",
                        VideoAnalysisJob.lease_expires_at.is_not(None),
                        VideoAnalysisJob.lease_expires_at <= now,
                    )
                    .order_by(VideoAnalysisJob.lease_expires_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(max(1, min(limit, 500)))
                )
            ).all()
        )
        if not jobs:
            await self.db.rollback()
            return 0
        video_ids = {job.video_id for job in jobs}
        videos = {
            video.id: video
            for video in (
                await self.db.scalars(select(VideoAsset).where(VideoAsset.id.in_(video_ids)))
            ).all()
        }
        for job in jobs:
            job.status = "failed"
            job.error = "Analysis worker heartbeat expired. Retry the analysis."
            job.finished_at = now
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.terminal_reason_code = "WORKER_LEASE_EXPIRED"
            job.terminal_stage = "worker_lease"
            video = videos.get(job.video_id)
            if video is not None:
                video.status = "analysis_failed"
        await self.db.commit()
        return len(jobs)

    async def list_jobs_by_ids(
        self, job_ids: list[str], *, org_id: int | None, user_id: int | None
    ) -> list[VideoAnalysisJob]:
        if not job_ids:
            return []
        stmt = select(VideoAnalysisJob).join(
            VideoAsset, VideoAsset.id == VideoAnalysisJob.video_id
        ).where(VideoAnalysisJob.id.in_(job_ids))
        stmt = stmt.where(
            org_or_owner_visibility(
                org_column=VideoAsset.org_id,
                owner_column=VideoAsset.uploaded_by_user_id,
                user_org_id=org_id,
                user_id=user_id or 0,
            )
        )
        return list((await self.db.scalars(stmt)).all())

    async def list_detections_by_job_ids(
        self, job_ids: list[str], *, org_id: int | None
    ) -> list[VideoDetection]:
        if not job_ids:
            return []
        stmt = select(VideoDetection).where(VideoDetection.job_id.in_(job_ids))
        stmt = stmt.where(self._visible_detection(org_id))
        stmt = stmt.order_by(
            VideoDetection.timestamp_seconds.asc(), VideoDetection.id.asc()
        )
        return list((await self.db.scalars(stmt)).all())

    async def page_detections_by_job_ids(
        self,
        job_ids: list[str],
        *,
        org_id: int | None,
        limit: int,
        after: tuple[float, str] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        min_confidence: float | None = None,
    ) -> tuple[list[VideoDetection], bool]:
        if not job_ids:
            return [], False
        bounded_limit = max(1, min(int(limit), 5000))
        stmt = select(VideoDetection).where(VideoDetection.job_id.in_(job_ids))
        stmt = stmt.where(self._visible_detection(org_id))
        filter_values = bbox or (None, None, None, None)
        stmt = self._apply_detection_filters(
            stmt,
            min_confidence=min_confidence,
            min_lon=filter_values[0],
            min_lat=filter_values[1],
            max_lon=filter_values[2],
            max_lat=filter_values[3],
        )
        if after is not None:
            timestamp, detection_id = after
            stmt = stmt.where(
                (VideoDetection.timestamp_seconds > timestamp)
                | (
                    (VideoDetection.timestamp_seconds == timestamp)
                    & (VideoDetection.id > detection_id)
                )
            )
        rows = list(
            (
                await self.db.scalars(
                    stmt.order_by(
                        VideoDetection.timestamp_seconds.asc(),
                        VideoDetection.id.asc(),
                    ).limit(bounded_limit + 1)
                )
            ).all()
        )
        return rows[:bounded_limit], len(rows) > bounded_limit

    async def aggregate_class_counts_by_job_ids(
        self,
        job_ids: list[str],
        *,
        org_id: int | None,
        bbox: tuple[float, float, float, float] | None = None,
        min_confidence: float | None = None,
    ) -> dict[str, int]:
        if not job_ids:
            return {}
        stmt = select(
            VideoDetection.label, func.count(VideoDetection.id)
        ).where(VideoDetection.job_id.in_(job_ids))
        stmt = stmt.where(self._visible_detection(org_id))
        filter_values = bbox or (None, None, None, None)
        stmt = self._apply_detection_filters(
            stmt,
            min_confidence=min_confidence,
            min_lon=filter_values[0],
            min_lat=filter_values[1],
            max_lon=filter_values[2],
            max_lat=filter_values[3],
        )
        rows = await self.db.execute(stmt.group_by(VideoDetection.label))
        return {str(label): int(count) for label, count in rows.all()}

    async def list_detections_for_user(
        self, job_id: str, user: User, limit: int = 500
    ) -> list[VideoDetection]:
        stmt = (
            select(VideoDetection)
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.job_id == job_id)
            .where(self._visible_video(user))
            .options(selectinload(VideoDetection.storage_object))
            .order_by(VideoDetection.timestamp_seconds.asc(), VideoDetection.id.asc())
            .limit(limit)
        )
        return list((await self.db.scalars(stmt)).all())

    async def page_detections_for_user(
        self,
        job_id: str,
        user: User,
        *,
        limit: int,
        after: tuple[float, str] | None = None,
        since_id: str | None = None,
        min_confidence: float | None = None,
        label: str | None = None,
        since_ts: float | None = None,
        until_ts: float | None = None,
    ) -> tuple[list[VideoDetection], bool, int]:
        visible = self._visible_video(user)
        stmt = (
            select(VideoDetection)
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.job_id == job_id, visible)
            .options(selectinload(VideoDetection.storage_object))
        )
        stmt = self._apply_detection_filters(
            stmt,
            min_confidence=min_confidence,
            label=label,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        if after is not None:
            timestamp, detection_id = after
            stmt = stmt.where(
                (VideoDetection.timestamp_seconds > timestamp)
                | (
                    (VideoDetection.timestamp_seconds == timestamp)
                    & (VideoDetection.id > detection_id)
                )
            )
        if since_id:
            anchor = await self.db.get(VideoDetection, since_id)
            if anchor is not None and anchor.job_id == job_id:
                stmt = stmt.where(
                    (VideoDetection.timestamp_seconds > anchor.timestamp_seconds)
                    | (
                        (VideoDetection.timestamp_seconds == anchor.timestamp_seconds)
                        & (VideoDetection.id > anchor.id)
                    )
                )
        rows = list(
            (
                await self.db.scalars(
                    stmt.order_by(
                        VideoDetection.timestamp_seconds.asc(), VideoDetection.id.asc()
                    ).limit(limit + 1)
                )
            ).all()
        )
        total_stmt = (
            select(func.count(VideoDetection.id))
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.job_id == job_id, visible)
        )
        total_stmt = self._apply_detection_filters(
            total_stmt,
            min_confidence=min_confidence,
            label=label,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        total = int(await self.db.scalar(total_stmt) or 0)
        return rows[:limit], len(rows) > limit, total

    async def get_detection_for_user(
        self, detection_id: str, user: User
    ) -> VideoDetection | None:
        return await self.db.scalar(
            select(VideoDetection)
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.id == detection_id, self._visible_video(user))
            .options(selectinload(VideoDetection.storage_object))
        )

    async def reconcile_staged_storage_objects(self, *, older_than_minutes: int) -> int:
        return await reconcile_staged_storage_objects(
            self.db,
            StorageObject,
            older_than_minutes=older_than_minutes,
        )

    async def summarize_detections(self, job_id: str, user: User) -> dict:
        visible = self._visible_video(user)
        counts = await self.db.execute(
            select(VideoDetection.label, func.count(VideoDetection.id))
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.job_id == job_id, visible)
            .group_by(VideoDetection.label)
        )
        tracked = await self.db.execute(
            select(VideoDetection.label, func.count(distinct(VideoDetection.track_id)))
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(
                VideoDetection.job_id == job_id,
                VideoDetection.track_id.is_not(None),
                visible,
            )
            .group_by(VideoDetection.label)
        )
        confidence = (
            await self.db.execute(
                select(
                    func.min(VideoDetection.confidence),
                    func.avg(VideoDetection.confidence),
                    func.max(VideoDetection.confidence),
                )
                .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
                .where(VideoDetection.job_id == job_id, visible)
            )
        ).one()
        return {
            "detections_by_class": {label: int(count) for label, count in counts.all()},
            "unique_tracked_objects_by_class": {
                label: int(count) for label, count in tracked.all()
            },
            "confidence_distribution": {
                "minimum": float(confidence[0]) if confidence[0] is not None else None,
                "mean": float(confidence[1]) if confidence[1] is not None else None,
                "maximum": float(confidence[2]) if confidence[2] is not None else None,
            },
        }

    async def aggregate_detections(
        self,
        job_id: str,
        user: User,
        *,
        bucket_seconds: float,
        min_confidence: float | None = None,
        label: str | None = None,
        since_ts: float | None = None,
        until_ts: float | None = None,
    ) -> list[dict]:
        visible = self._visible_video(user)
        # Truncation toward zero matches Python // for non-negative timestamps.
        bucket_index = cast(
            VideoDetection.timestamp_seconds / bucket_seconds, Integer
        )
        stmt = (
            select(
                bucket_index,
                VideoDetection.label,
                func.count(VideoDetection.id),
            )
            .join(VideoAsset, VideoAsset.id == VideoDetection.video_id)
            .where(VideoDetection.job_id == job_id, visible)
            .group_by(bucket_index, VideoDetection.label)
            .order_by(bucket_index.asc(), VideoDetection.label.asc())
        )
        stmt = self._apply_detection_filters(
            stmt,
            min_confidence=min_confidence,
            label=label,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        buckets: dict[int, dict[str, int]] = {}
        for index, class_label, count in (await self.db.execute(stmt)).all():
            counts = buckets.setdefault(int(index), {})
            counts[str(class_label)] = int(count)
        return [
            {
                "start_seconds": index * bucket_seconds,
                "end_seconds": (index + 1) * bucket_seconds,
                "class_counts": counts,
            }
            for index, counts in sorted(buckets.items())
        ]
