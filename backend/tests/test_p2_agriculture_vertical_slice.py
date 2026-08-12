from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.modules.agriculture import analysis_orchestration as orchestration_module
from backend.modules.agriculture import service as service_module
from backend.modules.agriculture.aggregation import aggregate_detections
from backend.modules.agriculture.analysis_orchestration import (
    AgricultureAnalysisOrchestration,
)
from backend.modules.video_analysis.contracts import (
    VideoDetectionRef,
    VideoJobRef,
    VideoSourceRef,
)
from backend.modules.vision_models.schemas import VisionProjectCreate


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Database:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = f"{type(value).__name__.lower()}-{len(self.added) + 1}"
        self.added.append(value)

    async def scalar(self, _statement):
        return None

    async def scalars(self, _statement):
        return _Rows([])

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def refresh(self, _value):
        return None


@pytest.mark.asyncio
async def test_create_run_ensure_jobs_and_aggregate_fake_detections(monkeypatch):
    async def no_existing_run(*_args, **_kwargs):
        return None

    source = VideoSourceRef(
        id="video-1",
        mission_id="mission-1",
        field_id=7,
        org_id=3,
        storage_path="/fixtures/flight.mp4",
        status="uploaded",
        fps=30,
        created_at=datetime.now(UTC),
    )
    submitted = []

    async def list_sources(*_args, **_kwargs):
        return [source]

    async def start_job(*_args, **kwargs):
        submitted.append(kwargs)
        return VideoJobRef(
            id="job-1",
            video_id="video-1",
            status="queued",
            model_version_id="vision-version-1",
            model_version="pending",
            source_checksum=None,
            progress=0,
            error=None,
            terminal_reason_code=None,
        )

    monkeypatch.setattr(
        service_module.agriculture_repository, "get_run_by_key", no_existing_run
    )
    monkeypatch.setattr(
        orchestration_module.video_analysis_port,
        "list_mission_sources",
        list_sources,
    )
    monkeypatch.setattr(
        orchestration_module.video_analysis_port,
        "start_or_reuse_job",
        start_job,
    )
    db = _Database()
    flight = SimpleNamespace(
        id="flight-1",
        mission_id="mission-1",
        field_id=7,
        org_id=3,
        input_manifest={"video_ids": ["video-1"]},
    )
    release = {
        "release_id": "release-1",
        "vision_model_version_id": "vision-version-1",
        "model_checksum": "a" * 64,
        "inference_profile": {
            "frame_stride_seconds": 1,
            "confidence_threshold": 0.4,
        },
    }

    run = await service_module.agriculture_service.create_analysis_run(
        db,
        flight=flight,
        values={
            "idempotency_key": "p2-slice",
            "analysis_profile": "standard",
            "requested_analyses": ["weed_detection"],
            "parameters": {},
            "model_versions": {"weed_detection": release},
            "calibration_versions": {},
            "baseline_flight_id": None,
            "requested_by_user_id": 9,
        },
    )
    links = await AgricultureAnalysisOrchestration().ensure_video_jobs(
        db,
        run=run,
        flight=flight,
        user=SimpleNamespace(id=9),
    )
    detections = [
        VideoDetectionRef(
            id="det-1",
            job_id="job-1",
            video_id="video-1",
            mission_id="mission-1",
            frame_index=1,
            timestamp_seconds=1,
            label="weed",
            confidence=0.9,
            x1=1,
            y1=1,
            x2=10,
            y2=10,
            track_id=4,
            lat=50,
            lon=4,
            altitude_m=12,
            heading_deg=0,
            storage_object_id=None,
            raw={"model_version": "vision-version-1"},
        )
    ]
    findings = aggregate_detections(detections)

    assert run.flight_id == "flight-1"
    assert submitted[0]["video_id"] == "video-1"
    assert links[0].video_job_id == "job-1"
    assert findings[0]["observation_type"] == "weed"
    assert findings[0]["evidence_ids"] == ["det-1"]


def test_instance_segmentation_is_soft_disabled_with_clear_error():
    with pytest.raises(ValidationError, match="instance_segmentation is not supported"):
        VisionProjectCreate.model_validate(
            {
                "name": "segmentation request",
                "crop": "corn",
                "task_type": "instance_segmentation",
                "classes": [{"name": "weed"}],
            }
        )
