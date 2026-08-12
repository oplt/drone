from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from backend.modules.video_analysis import application as application_module
from backend.modules.video_analysis.application import VideoAnalysisApplication
from backend.modules.video_analysis.schemas import AnalyzeVideoRequest
from backend.modules.video_analysis.service import detector as detector_module
from backend.modules.video_analysis.service import pipeline as pipeline_module
from backend.modules.video_analysis.service.detector import (
    FrameDetection,
    SahiYoloFrameDetector,
    _resolved_model_path,
    create_frame_detector,
)
from backend.modules.video_analysis.service.pipeline import OfflineVideoAnalysisPipeline
from backend.modules.video_analysis.service.tracker import FrameTracker


def detection(x: float, *, label: str = "tomato") -> FrameDetection:
    return FrameDetection(
        label=label,
        confidence=0.9,
        x1=x,
        y1=100,
        x2=x + 40,
        y2=140,
        raw={},
    )


def test_bytetrack_keeps_identity_for_moving_objects_and_isolates_jobs():
    first_job = FrameTracker(sampled_frame_rate=10)
    track_ids = [first_job.update([detection(x)])[0].track_id for x in (100, 105, 111)]
    assert track_ids == [1, 1, 1]

    two_objects = first_job.update([detection(116), detection(300)])
    assert two_objects[0].track_id == 1
    first_job.update([])
    first_job.update([detection(121)])

    second_job = FrameTracker(sampled_frame_rate=10)
    assert second_job.update([detection(100)])[0].track_id == 1
    assert second_job.global_ids == {("tomato", 1): 1}


def test_tracker_is_class_aware():
    tracker = FrameTracker(sampled_frame_rate=10)
    output = tracker.update([detection(100, label="ripe"), detection(100, label="damaged")])
    assert output[0].track_id != output[1].track_id


def test_tracking_request_requires_dense_sampling():
    defaults = AnalyzeVideoRequest()
    assert defaults.tracking_enabled is False
    assert defaults.small_object_mode is False
    request = AnalyzeVideoRequest(tracking_enabled=True, frame_stride_seconds=1.5)
    assert request.tracker_type == "bytetrack"
    with pytest.raises(ValidationError, match="2 seconds or less"):
        AnalyzeVideoRequest(tracking_enabled=True, frame_stride_seconds=3)


def test_detector_factory_selects_standard_or_sahi(monkeypatch):
    calls: list[str] = []

    class Standard:
        def __init__(self, **_kwargs):
            calls.append("standard")

    class Sahi:
        def __init__(self, **_kwargs):
            calls.append("sahi")

    monkeypatch.setattr(detector_module, "YoloFrameDetector", Standard)
    monkeypatch.setattr(detector_module, "SahiYoloFrameDetector", Sahi)
    create_frame_detector("yolo26n.pt", small_object_mode=False)
    create_frame_detector("registered", model_path="/managed/model.pt", small_object_mode=True)
    assert calls == ["standard", "sahi"]


def test_sahi_predictions_keep_full_frame_coordinates(monkeypatch):
    captured: dict[str, object] = {}

    def sliced_prediction(image, model, **kwargs):
        captured.update({"shape": image.shape, "model": model, **kwargs})
        prediction = SimpleNamespace(
            bbox=SimpleNamespace(to_xyxy=lambda: [702.5, 412.0, 755.0, 480.25]),
            category=SimpleNamespace(id=3, name="ripe_tomato"),
            score=SimpleNamespace(value=0.91),
        )
        return SimpleNamespace(object_prediction_list=[prediction])

    sahi = ModuleType("sahi")
    sahi.__path__ = []
    sahi_predict = ModuleType("sahi.predict")
    sahi_predict.get_sliced_prediction = sliced_prediction
    monkeypatch.setitem(sys.modules, "sahi", sahi)
    monkeypatch.setitem(sys.modules, "sahi.predict", sahi_predict)

    detector = SahiYoloFrameDetector.__new__(SahiYoloFrameDetector)
    detector.model_name = "registered-model"
    detector.model_version = "checksum"
    detector.model = object()
    detector.slice_height = 640
    detector.slice_width = 640
    detector.overlap_height_ratio = 0.2
    detector.overlap_width_ratio = 0.2
    detector.postprocess_match_threshold = 0.5
    output = detector.predict(np.zeros((1080, 1920, 3), dtype=np.uint8))

    assert output[0].x1 == pytest.approx(702.5)
    assert output[0].y2 == pytest.approx(480.25)
    assert output[0].raw["inference_mode"] == "sahi"
    assert captured["shape"] == (1080, 1920, 3)
    assert captured["perform_standard_pred"] is True
    assert captured["postprocess_class_agnostic"] is False


def test_detector_model_resolution_supports_registered_and_builtin_weights(
    tmp_path, monkeypatch
):
    registered = tmp_path / "registered.pt"
    registered.write_bytes(b"registered")
    builtin = tmp_path / "builtin.pt"
    builtin.write_bytes(b"builtin")
    calls: list[str] = []

    def ensure(name: str) -> Path:
        calls.append(name)
        return builtin

    monkeypatch.setattr(detector_module, "ensure_model_file", ensure)
    assert _resolved_model_path("registered", registered) == registered.resolve()
    assert _resolved_model_path("yolo26n.pt", None) == builtin.resolve()
    assert calls == ["yolo26n.pt"]


class PipelineRepository:
    def __init__(self, job, video):
        self.job = job
        self.video = video
        self.saved = []
        self.failure: str | None = None

    async def get_job(self, _job_id):
        return self.job

    async def get_video(self, _video_id):
        return self.video

    async def mark_job_running(self, _job):
        self.job.status = "running"

    async def set_source_checksum(self, _job, checksum):
        self.job.source_checksum = checksum

    async def update_video_metadata(self, _video, **_kwargs):
        return None

    async def set_model_version(self, _job, version):
        self.job.model_version = version

    async def flush_batch(self, detections, **_kwargs):
        self.saved.extend(detections)

    async def update_processing_metrics(self, _job, **values):
        for key, value in values.items():
            setattr(self.job, key, value)

    async def set_video_status(self, _video, status):
        self.video.status = status

    async def mark_job_completed(self, _job):
        self.job.status = "completed"

    async def mark_job_failed(self, _job, error):
        self.job.status = "failed"
        self.failure = error


def pipeline_context(tmp_path, *, tracking: bool, small_objects: bool):
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"deterministic source")
    job = SimpleNamespace(
        id="job-1",
        video_id="video-1",
        org_id=7,
        model_name="yolo26n.pt",
        model_version_id=None,
        model_version="",
        small_object_mode=small_objects,
        tracking_enabled=tracking,
        tracker_type="bytetrack",
        frame_stride_seconds=0.1,
        confidence_threshold=0.35,
        status="queued",
    )
    video = SimpleNamespace(
        id="video-1",
        storage_path=str(video_path),
        mission_id=None,
        org_id=7,
        uploaded_by_user_id=1,
        created_at=datetime.now(UTC),
        status="uploaded",
    )
    repository = PipelineRepository(job, video)
    pipeline = OfflineVideoAnalysisPipeline(
        SimpleNamespace(rollback=_async_noop), evidence_root=tmp_path / "evidence"
    )
    pipeline.repo = repository
    pipeline._save_crop = lambda **_kwargs: None
    return pipeline, repository


async def _async_noop(*_args, **_kwargs):
    return None


async def inline(function, *args, **kwargs):
    ignored = {"boundary", "operation", "timeout_s"}
    return function(*args, **{key: value for key, value in kwargs.items() if key not in ignored})


@pytest.mark.asyncio
async def test_sahi_pipeline_composes_with_job_local_tracker(tmp_path, monkeypatch):
    pipeline, repository = pipeline_context(tmp_path, tracking=True, small_objects=True)
    detector_calls: list[dict[str, object]] = []

    class Detector:
        model_version = "fake-sahi-v1"

        def __init__(self):
            self.frame = 0

        def predict(self, _image):
            self.frame += 1
            return [detection(100 + self.frame * 5)]

    detector = Detector()

    def create(**kwargs):
        detector_calls.append(kwargs)
        return detector

    async def frames(*_args, **_kwargs):
        for index in range(3):
            yield SimpleNamespace(
                frame_index=index,
                timestamp_seconds=index / 10,
                image_bgr=np.zeros((240, 320, 3), dtype=np.uint8),
            )

    monkeypatch.setattr(pipeline_module, "run_blocking", inline)
    monkeypatch.setattr(pipeline_module, "create_frame_detector", create)
    monkeypatch.setattr(pipeline_module, "async_iter_frames", frames)
    monkeypatch.setattr(
        pipeline_module,
        "read_video_metadata_async",
        lambda _path: _async_value(
            SimpleNamespace(fps=30.0, width=320, height=240, duration_seconds=0.3)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.agriculture_repository,
        "list_telemetry",
        _async_value,
    )

    await pipeline.run("job-1")

    assert repository.job.status == "completed"
    assert detector_calls[0]["small_object_mode"] is True
    assert [item.track_id for item in repository.saved] == [1, 1, 1]
    assert all(item.raw["small_object_mode"] for item in repository.saved)
    assert all(item.raw["tracking_enabled"] for item in repository.saved)


async def _async_value(value=None, *_args, **_kwargs):
    return value


@pytest.mark.asyncio
async def test_sahi_failure_marks_analysis_job_failed(tmp_path, monkeypatch):
    pipeline, repository = pipeline_context(tmp_path, tracking=True, small_objects=True)

    class BrokenDetector:
        model_version = "broken"

        def predict(self, _image):
            raise RuntimeError("slice failure")

    async def frames(*_args, **_kwargs):
        yield SimpleNamespace(
            frame_index=0,
            timestamp_seconds=0.0,
            image_bgr=np.zeros((240, 320, 3), dtype=np.uint8),
        )

    monkeypatch.setattr(pipeline_module, "run_blocking", inline)
    monkeypatch.setattr(
        pipeline_module, "create_frame_detector", lambda **_kwargs: BrokenDetector()
    )
    monkeypatch.setattr(pipeline_module, "async_iter_frames", frames)
    monkeypatch.setattr(
        pipeline_module,
        "read_video_metadata_async",
        lambda _path: _async_value(
            SimpleNamespace(fps=30.0, width=320, height=240, duration_seconds=0.1)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.agriculture_repository,
        "list_telemetry",
        _async_value,
    )

    with pytest.raises(RuntimeError, match="Small-object analysis failed"):
        await pipeline.run("job-1")

    assert repository.job.status == "failed"
    assert repository.failure == "Small-object analysis failed. Check worker logs for details."


@pytest.mark.asyncio
async def test_summary_reports_unique_tracks_and_reproducibility(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        frames_processed=3,
        model_name="Tomato detector v1",
        model_version="registered:version-1:checksum",
        model_version_id=None,
        tracking_enabled=True,
        tracker_type="bytetrack",
        small_object_mode=True,
        frame_stride_seconds=0.1,
        confidence_threshold=0.35,
    )

    class Repository:
        def __init__(self, _db):
            pass

        async def get_job_for_user(self, job_id, _user):
            return job if job_id == job.id else None

        async def summarize_detections(self, _job_id, _user):
            return {
                "detections_by_class": {"ripe": 3},
                "unique_tracked_objects_by_class": {"ripe": 1},
                "confidence_distribution": {
                    "minimum": 0.8,
                    "mean": 0.9,
                    "maximum": 0.95,
                },
            }

    monkeypatch.setattr(application_module, "VideoAnalysisRepository", Repository)
    summary = await VideoAnalysisApplication().get_summary(
        SimpleNamespace(), job_id=job.id, user=SimpleNamespace(id=1, org_id=7)
    )

    assert summary["unique_tracked_objects_by_class"] == {"ripe": 1}
    assert summary["frames_analyzed"] == 3
    assert summary["tracking_enabled"] is True
    assert summary["small_object_mode"] is True
