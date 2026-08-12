from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database.base import Base
from backend.modules.video_analysis.models import (
    VideoAnalysisJob,
    VideoAsset,
    VideoDetection,
)
from backend.modules.video_analysis.repository import VideoAnalysisRepository

DETECTION_COUNT = 2500
PAGE_SIZE = 200
BUCKET_SECONDS = 10.0


@pytest_asyncio.fixture
async def detection_scale_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    VideoAsset.__table__,
                    VideoAnalysisJob.__table__,
                    VideoDetection.__table__,
                ],
            )
        )
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_factory() as session:
        video = VideoAsset(
            id="video-scale-1",
            original_filename="scale.mp4",
            storage_path="/tmp/scale.mp4",
            org_id=7,
            uploaded_by_user_id=3,
            status="uploaded",
        )
        job = VideoAnalysisJob(
            id="job-scale-1",
            video_id=video.id,
            org_id=7,
            status="completed",
            model_name="yolo26s.pt",
        )
        session.add_all([video, job])

        detections: list[VideoDetection] = []
        for index in range(DETECTION_COUNT):
            label = "weed" if index % 2 == 0 else "pest"
            track_id = (index % 50) if index % 3 == 0 else None
            detections.append(
                VideoDetection(
                    id=f"det-{index:05d}",
                    job_id=job.id,
                    video_id=video.id,
                    org_id=7,
                    frame_index=index,
                    timestamp_seconds=float(index) * 0.5,
                    label=label,
                    confidence=0.4 + (index % 60) / 100.0,
                    x1=0.0,
                    y1=0.0,
                    x2=1.0,
                    y2=1.0,
                    track_id=track_id,
                )
            )
        session.add_all(detections)
        await session.commit()
        yield session, job.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_aggregate_bucket_totals_cover_full_detection_set(detection_scale_db):
    db, job_id = detection_scale_db
    user = SimpleNamespace(id=3, org_id=7)
    repo = VideoAnalysisRepository(db)

    buckets = await repo.aggregate_detections(
        job_id, user, bucket_seconds=BUCKET_SECONDS
    )
    total = sum(sum(bucket["class_counts"].values()) for bucket in buckets)

    assert DETECTION_COUNT > 2000
    assert total == DETECTION_COUNT
    assert buckets[0]["start_seconds"] == 0.0
    assert buckets[0]["end_seconds"] == BUCKET_SECONDS


@pytest.mark.asyncio
async def test_summarize_detections_unique_tracked_counts(detection_scale_db):
    db, job_id = detection_scale_db
    user = SimpleNamespace(id=3, org_id=7)
    repo = VideoAnalysisRepository(db)

    summary = await repo.summarize_detections(job_id, user)

    assert summary["detections_by_class"]["weed"] + summary["detections_by_class"][
        "pest"
    ] == DETECTION_COUNT
    # Every third detection has track_id in 0..49 alternating labels by even/odd index.
    assert summary["unique_tracked_objects_by_class"]["weed"] == 25
    assert summary["unique_tracked_objects_by_class"]["pest"] == 25
    assert summary["confidence_distribution"]["minimum"] is not None
    assert summary["confidence_distribution"]["maximum"] is not None


@pytest.mark.asyncio
async def test_page_detections_has_more_and_filters(detection_scale_db):
    db, job_id = detection_scale_db
    user = SimpleNamespace(id=3, org_id=7)
    repo = VideoAnalysisRepository(db)

    first_page, has_more, total = await repo.page_detections_for_user(
        job_id, user, limit=PAGE_SIZE
    )
    assert total == DETECTION_COUNT
    assert has_more is True
    assert len(first_page) == PAGE_SIZE

    seen: set[str] = {row.id for row in first_page}
    after = (first_page[-1].timestamp_seconds, first_page[-1].id)
    pages = 1
    while has_more:
        page, has_more, page_total = await repo.page_detections_for_user(
            job_id, user, limit=PAGE_SIZE, after=after
        )
        assert page_total == DETECTION_COUNT
        assert page
        for row in page:
            assert row.id not in seen
            seen.add(row.id)
        after = (page[-1].timestamp_seconds, page[-1].id)
        pages += 1
        assert pages < 50

    assert len(seen) == DETECTION_COUNT
    assert has_more is False

    filtered, filtered_more, filtered_total = await repo.page_detections_for_user(
        job_id,
        user,
        limit=PAGE_SIZE,
        label="weed",
        min_confidence=0.7,
        since_ts=100.0,
        until_ts=200.0,
    )
    expected_filtered = sum(
        1
        for index in range(DETECTION_COUNT)
        if index % 2 == 0
        and 0.4 + (index % 60) / 100.0 >= 0.7
        and 100.0 <= index * 0.5 <= 200.0
    )
    assert filtered_total == expected_filtered
    assert all(
        row.label == "weed"
        and row.confidence >= 0.7
        and 100.0 <= row.timestamp_seconds <= 200.0
        for row in filtered
    )
    if filtered_total > PAGE_SIZE:
        assert filtered_more is True
    else:
        assert filtered_more is False
        assert len(filtered) == filtered_total

    weed_buckets = await repo.aggregate_detections(
        job_id,
        user,
        bucket_seconds=BUCKET_SECONDS,
        label="weed",
        min_confidence=0.7,
        since_ts=100.0,
        until_ts=200.0,
    )
    assert sum(sum(bucket["class_counts"].values()) for bucket in weed_buckets) == (
        filtered_total
    )
    assert all(set(bucket["class_counts"]) <= {"weed"} for bucket in weed_buckets)
