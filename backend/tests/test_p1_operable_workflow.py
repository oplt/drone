from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import HTTPException

from backend.modules.video_analysis import api as video_api
from backend.modules.video_analysis.models import StorageObject, VideoAnalysisJob
from backend.modules.video_analysis.schemas import VideoAssetOut, VideoDetectionOut
from backend.modules.video_analysis.service.pipeline import OfflineVideoAnalysisPipeline


def _detection(**overrides):
    storage = overrides.pop("storage_object", None)
    values = {
        "id": "det-1",
        "job_id": "job-1",
        "video_id": "video-1",
        "mission_id": "mission-1",
        "frame_index": 4,
        "timestamp_seconds": 2.5,
        "label": "weed",
        "confidence": 0.9,
        "x1": 1.0,
        "y1": 2.0,
        "x2": 10.0,
        "y2": 12.0,
        "track_id": None,
        "lat": 50.0,
        "lon": 4.0,
        "altitude_m": 12.0,
        "heading_deg": 20.0,
        "evidence_path": "/host/private/crop.jpg",
        "storage_object": storage,
        "raw": {
            "telemetry_match_quality": "low_confidence_upload_time",
            "telemetry_match_delta_ms": 850.0,
            "telemetry_match_method": "nearest",
            "telemetry_match_version": "nearest-telemetry.v1",
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_detection_output_never_serializes_local_evidence_path():
    storage = SimpleNamespace(
        id="object-1", checksum="a" * 64, state="final"
    )
    output = VideoDetectionOut.model_validate(_detection(storage_object=storage))
    payload = output.model_dump()
    assert payload["evidence_path"] is None
    assert "/host/" not in str(payload)
    assert output.evidence is not None
    assert output.evidence.storage_object_id == "object-1"
    assert output.telemetry_match_quality == "low_confidence_upload_time"


def test_capture_time_contract_and_stage_timings_defaults_are_present():
    captured = datetime(2026, 8, 1, tzinfo=UTC)
    asset = VideoAssetOut.model_validate(
        {
            "id": "video-1",
            "original_filename": "flight.mp4",
            "status": "uploaded",
            "captured_at": captured,
            "capture_time_source": "operator",
            "sync_offset_seconds": 1.25,
            "created_at": datetime.now(UTC),
        }
    )
    assert asset.captured_at == captured
    assert asset.capture_time_source == "operator"
    assert VideoAnalysisJob(stage_timings={}).stage_timings == {}


@pytest.mark.asyncio
async def test_cursor_page_reports_has_more(monkeypatch):
    rows = [_detection(id="det-1"), _detection(id="det-2", timestamp_seconds=3.0)]

    async def get_job(*_args, **_kwargs):
        return SimpleNamespace(attempt=2, status="running")

    async def page(*_args, **_kwargs):
        return rows, True, 10

    monkeypatch.setattr(
        "backend.modules.video_analysis.repository.VideoAnalysisRepository.get_job_for_user",
        get_job,
    )
    monkeypatch.setattr(
        "backend.modules.video_analysis.repository.VideoAnalysisRepository.page_detections_for_user",
        page,
    )
    result = await video_api.application.page_detections(
        SimpleNamespace(),
        job_id="job-1",
        user=SimpleNamespace(),
        limit=2,
        cursor=None,
        since_id=None,
    )
    assert result["has_more"] is True
    assert result["next_cursor"]
    assert result["job_version"] == 2


@pytest.mark.asyncio
async def test_evidence_resolver_returns_url_without_backend_key(monkeypatch):
    storage = SimpleNamespace(
        id="object-1",
        checksum="b" * 64,
        state="final",
        backend_key="/host/private/crop.jpg",
        mime="image/jpeg",
    )

    async def get_detection(*_args, **_kwargs):
        return _detection(storage_object=storage)

    monkeypatch.setattr(
        "backend.modules.video_analysis.repository.VideoAnalysisRepository.get_detection_for_user",
        get_detection,
    )
    result = await video_api.application.resolve_evidence(
        SimpleNamespace(), detection_id="det-1", user=SimpleNamespace()
    )
    assert result["evidence_path"] is None
    assert result["evidence_url"].endswith("/det-1/content")
    assert "/host/private" not in str(result)


@pytest.mark.asyncio
async def test_query_token_is_rejected_when_disabled(monkeypatch):
    monkeypatch.setattr(video_api.settings, "allow_media_query_token", False)
    with pytest.raises(HTTPException) as exc:
        await video_api.stream_video(
            "video-1",
            token="secret",
            db=SimpleNamespace(),
            user=SimpleNamespace(),
        )
    assert exc.value.status_code == 401


def test_crop_policy_and_successful_storage_object_registration(tmp_path: Path):
    pipeline = OfflineVideoAnalysisPipeline(
        SimpleNamespace(), evidence_root=tmp_path
    )
    assert pipeline.should_store_crop(confidence=0.99, track_id=None)
    assert pipeline.should_store_crop(confidence=0.1, track_id=7)
    assert not pipeline.should_store_crop(confidence=0.1, track_id=None)
    crop = pipeline._save_crop(
        job_id="job-1",
        frame_index=1,
        detection_index=0,
        image_bgr=np.full((20, 20, 3), 255, dtype=np.uint8),
        xyxy=(1, 1, 10, 10),
    )
    assert crop is not None
    path, checksum, size = crop
    storage = StorageObject(
        checksum=checksum,
        size=size,
        mime="image/jpeg",
        owner_type="video_detection",
        owner_id="det-1",
        state="final",
        retention_policy="analysis_evidence",
        backend_key=str(path),
    )
    assert path.is_file()
    assert storage.checksum == checksum
    assert storage.state == "final"
