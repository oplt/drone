from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity.models import User
from backend.modules.video_analysis.models import (
    VideoAnalysisJob,
    VideoAsset,
    VideoDetection,
)
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.schemas import AnalyzeVideoRequest


@dataclass(frozen=True, slots=True)
class VideoSourceRef:
    id: str
    mission_id: str | None
    field_id: int | None
    org_id: int | None
    status: str
    fps: float | None
    created_at: datetime
    captured_at: datetime | None = None
    capture_time_source: str = "unknown"


@dataclass(frozen=True, slots=True)
class VideoJobRef:
    id: str
    video_id: str
    status: str
    model_version_id: str | None
    model_version: str
    source_checksum: str | None
    progress: float
    error: str | None
    terminal_reason_code: str | None
    loaded_model_hash: str | None = None


@dataclass(frozen=True, slots=True)
class VideoDetectionRef:
    id: str
    job_id: str
    video_id: str
    mission_id: str | None
    frame_index: int
    timestamp_seconds: float
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    track_id: int | None
    lat: float | None
    lon: float | None
    altitude_m: float | None
    heading_deg: float | None
    storage_object_id: str | None
    raw: dict[str, Any] | None


def _source_ref(value: VideoAsset) -> VideoSourceRef:
    return VideoSourceRef(
        id=value.id,
        mission_id=value.mission_id,
        field_id=value.field_id,
        org_id=value.org_id,
        status=value.status,
        fps=value.fps,
        created_at=value.created_at,
        captured_at=value.captured_at,
        capture_time_source=value.capture_time_source,
    )


def _job_ref(value: VideoAnalysisJob) -> VideoJobRef:
    return VideoJobRef(
        id=value.id,
        video_id=value.video_id,
        status=value.status,
        model_version_id=value.model_version_id,
        model_version=value.model_version,
        loaded_model_hash=getattr(value, "loaded_model_hash", None),
        source_checksum=value.source_checksum,
        progress=value.progress,
        error=value.error,
        terminal_reason_code=value.terminal_reason_code,
    )


def _detection_ref(value: VideoDetection) -> VideoDetectionRef:
    return VideoDetectionRef(
        id=value.id,
        job_id=value.job_id,
        video_id=value.video_id,
        mission_id=value.mission_id,
        frame_index=value.frame_index,
        timestamp_seconds=value.timestamp_seconds,
        label=value.label,
        confidence=value.confidence,
        x1=value.x1,
        y1=value.y1,
        x2=value.x2,
        y2=value.y2,
        track_id=value.track_id,
        lat=value.lat,
        lon=value.lon,
        altitude_m=value.altitude_m,
        heading_deg=value.heading_deg,
        storage_object_id=value.storage_object_id,
        raw=dict(value.raw or {}),
    )


class VideoAnalysisPort:
    """Typed in-process boundary used by Agriculture orchestration."""

    async def list_mission_sources(
        self,
        db: AsyncSession,
        *,
        mission_id: str,
        org_id: int | None,
        user_id: int | None,
    ) -> list[VideoSourceRef]:
        rows = await VideoAnalysisRepository(db).list_videos_for_scope(
            mission_id=mission_id,
            org_id=org_id,
            user_id=user_id,
        )
        return [_source_ref(row) for row in rows]

    async def get_source_for_user(
        self,
        db: AsyncSession,
        video_id: str,
        user: User,
    ) -> VideoSourceRef | None:
        row = await VideoAnalysisRepository(db).get_video_for_user(video_id, user)
        return _source_ref(row) if row is not None else None

    async def resolve_source_media_path(
        self,
        db: AsyncSession,
        *,
        video_id: str,
        org_id: int | None,
    ) -> str:
        row = await VideoAnalysisRepository(db).get_video(video_id)
        if row is None or row.org_id != org_id:
            raise LookupError("Video source is not available in this scope")
        if not Path(row.storage_path).is_file():
            raise LookupError("Video source is not available on disk")
        return row.storage_path

    async def start_or_reuse_job(
        self,
        db: AsyncSession,
        *,
        video_id: str,
        request: AnalyzeVideoRequest,
        user: User,
        orchestration_key: str,
    ) -> VideoJobRef:
        from backend.modules.video_analysis.application import VideoAnalysisApplication

        job = await VideoAnalysisApplication().start_analysis(
            db,
            video_id=video_id,
            request=request,
            user=user,
            orchestration_key=orchestration_key,
        )
        return _job_ref(job)

    async def list_jobs(
        self,
        db: AsyncSession,
        *,
        job_ids: list[str],
        org_id: int | None,
        user_id: int | None,
    ) -> list[VideoJobRef]:
        rows = await VideoAnalysisRepository(db).list_jobs_by_ids(
            job_ids, org_id=org_id, user_id=user_id
        )
        return [_job_ref(row) for row in rows]

    async def list_detections(
        self,
        db: AsyncSession,
        *,
        job_ids: list[str],
        org_id: int | None,
        limit: int = 5000,
        cursor: tuple[float, str] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        min_confidence: float | None = None,
    ) -> list[VideoDetectionRef]:
        """Return one bounded page; callers processing all rows should iterate pages."""
        rows, _ = await VideoAnalysisRepository(db).page_detections_by_job_ids(
            job_ids,
            org_id=org_id,
            limit=min(max(1, int(limit)), 5000),
            after=cursor,
            bbox=bbox,
            min_confidence=min_confidence,
        )
        return [_detection_ref(row) for row in rows]

    async def iter_detection_pages(
        self,
        db: AsyncSession,
        *,
        job_ids: list[str],
        org_id: int | None,
        page_size: int = 1000,
        bbox: tuple[float, float, float, float] | None = None,
        min_confidence: float | None = None,
    ) -> AsyncIterator[list[VideoDetectionRef]]:
        cursor: tuple[float, str] | None = None
        while True:
            rows, has_more = await VideoAnalysisRepository(
                db
            ).page_detections_by_job_ids(
                job_ids,
                org_id=org_id,
                limit=min(max(1, int(page_size)), 5000),
                after=cursor,
                bbox=bbox,
                min_confidence=min_confidence,
            )
            if not rows:
                return
            yield [_detection_ref(row) for row in rows]
            if not has_more:
                return
            last = rows[-1]
            cursor = (last.timestamp_seconds, last.id)

    async def aggregate_detection_counts(
        self,
        db: AsyncSession,
        *,
        job_ids: list[str],
        org_id: int | None,
        bbox: tuple[float, float, float, float] | None = None,
        min_confidence: float | None = None,
    ) -> dict[str, int]:
        return await VideoAnalysisRepository(db).aggregate_class_counts_by_job_ids(
            job_ids,
            org_id=org_id,
            bbox=bbox,
            min_confidence=min_confidence,
        )

    async def cancel_jobs(
        self,
        db: AsyncSession,
        *,
        job_ids: list[str],
        user: User,
    ) -> None:
        repo = VideoAnalysisRepository(db)
        for job_id in sorted(set(job_ids)):
            await repo.cancel_job(job_id, user=user)


video_analysis_port = VideoAnalysisPort()
