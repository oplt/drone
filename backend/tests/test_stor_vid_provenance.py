from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.modules.agriculture.contracts import MissionTelemetrySample
from backend.modules.agriculture.georeferencing import interpolate_pose
from backend.modules.video_analysis.application import VideoAnalysisApplication
from backend.modules.video_analysis.models import StorageObject
from backend.modules.video_analysis.repository import VideoAnalysisRepository
from backend.modules.video_analysis.schemas import (
    VideoCaptureMetadataPatch,
    VideoDetectionOut,
)
from backend.modules.video_analysis.service.geo import NearestTelemetryMatcher
from backend.tests.test_p1_operable_workflow import _detection


@pytest.mark.asyncio
async def test_reconcile_staged_storage_objects_marks_orphans():
    cutoff_age = datetime.now(UTC) - timedelta(minutes=45)
    staged = StorageObject(
        id="staged-1",
        checksum="a" * 64,
        size=12,
        mime="image/jpeg",
        owner_type="video_detection",
        owner_id="det-1",
        state="staged",
        retention_policy="analysis_evidence",
        backend_key="crops/job-1/frame_00000001_det_000.jpg",
    )
    staged.created_at = cutoff_age

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    commits = {"count": 0}

    async def scalars(_stmt):
        return _Result([staged])

    async def commit():
        commits["count"] += 1

    db = SimpleNamespace(scalars=scalars, commit=commit)
    count = await VideoAnalysisRepository(db).reconcile_staged_storage_objects(
        older_than_minutes=30
    )
    assert count == 1
    assert staged.state == "orphan"
    assert commits["count"] == 1

def test_evidence_content_path_dual_reads_relative_and_absolute(tmp_path, monkeypatch):
    relative = "crops/job-1/frame_00000001_det_000.jpg"
    absolute = tmp_path / "legacy" / "crop.jpg"
    absolute.parent.mkdir(parents=True)
    absolute.write_bytes(b"abs")
    (tmp_path / relative).parent.mkdir(parents=True)
    (tmp_path / relative).write_bytes(b"rel")

    monkeypatch.setattr(
        "backend.modules.video_analysis.application.EVIDENCE_ROOT",
        tmp_path,
    )
    app = VideoAnalysisApplication()
    assert app._resolve_storage_path(relative) == tmp_path / relative
    assert app._resolve_storage_path(str(absolute)) == absolute
    assert app._resolve_storage_path("missing/crop.jpg") is None


def test_telemetry_match_includes_sample_ids_and_method():
    start = datetime(2026, 8, 12, 10, tzinfo=UTC)
    samples = [
        MissionTelemetrySample(
            id=11,
            timestamp_utc=start,
            lat=50.0,
            lon=4.0,
            relative_altitude_m=12.0,
            yaw_deg=90.0,
        ),
        MissionTelemetrySample(
            id=12,
            timestamp_utc=start + timedelta(seconds=2),
            lat=50.001,
            lon=4.001,
            relative_altitude_m=13.0,
            yaw_deg=95.0,
        ),
    ]
    nearest = interpolate_pose(samples, start)
    assert nearest.status == "nearest"
    assert nearest.sample_ids == (11,)

    interpolated = interpolate_pose(samples, start + timedelta(seconds=1))
    assert interpolated.status == "interpolated"
    assert interpolated.sample_ids == (11, 12)

    match = NearestTelemetryMatcher("mission-1", samples, start).match(1.0)
    assert match.method == "interpolated"
    assert match.sample_ids == (11, 12)


def test_video_detection_out_exposes_capture_provenance_fields():
    output = VideoDetectionOut.model_validate(
        _detection(
            raw={
                "telemetry_match_quality": "interpolated",
                "telemetry_match_delta_ms": 0.0,
                "telemetry_match_method": "interpolated",
                "telemetry_match_version": "nearest-telemetry.v1",
                "telemetry_sample_ids": [11, 12],
                "capture_time_source": "operator",
                "sync_offset_seconds": 1.5,
                "capture_time_uncertainty_seconds": 2.0,
            }
        )
    )
    assert output.telemetry_match_method == "interpolated"
    assert output.telemetry_sample_ids == [11, 12]
    assert output.capture_time_source == "operator"
    assert output.sync_offset_seconds == 1.5
    assert output.capture_time_uncertainty_seconds == 2.0
    assert output.evidence_path is None


@pytest.mark.asyncio
async def test_capture_metadata_patch_sets_reanalysis_required(monkeypatch):
    video = SimpleNamespace(
        id="video-1",
        captured_at=None,
        capture_timezone=None,
        sync_offset_seconds=0.0,
        capture_time_source="upload_time",
        reanalysis_required=False,
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    repo = SimpleNamespace(
        get_video_for_user=AsyncMock(return_value=video),
        video_has_analyzed_jobs=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "backend.modules.video_analysis.application.VideoAnalysisRepository",
        lambda _db: repo,
    )
    audits: list[dict] = []
    monkeypatch.setattr(
        "backend.modules.video_analysis.application.emit_audit_event",
        lambda **kwargs: audits.append(kwargs),
    )

    captured = datetime(2026, 8, 1, 12, tzinfo=UTC)
    result = await VideoAnalysisApplication().update_capture_metadata(
        db,
        video_id="video-1",
        user=SimpleNamespace(id=7),
        patch=VideoCaptureMetadataPatch(
            captured_at=captured,
            sync_offset_seconds=2.5,
            capture_timezone="Europe/Brussels",
        ),
    )
    assert result.captured_at == captured
    assert result.capture_time_source == "operator"
    assert result.sync_offset_seconds == 2.5
    assert result.reanalysis_required is True
    assert audits[0]["event_name"] == "video_capture_metadata_updated"
