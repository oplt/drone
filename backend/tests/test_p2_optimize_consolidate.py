from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import cv2
import numpy as np
import pytest
from starlette.requests import Request

from backend.core.api_errors import domain_api_error_handler
from backend.modules.video_analysis.model_storage import ModelArtifactIntegrityError
from backend.modules.video_analysis.schemas import VideoDetectionOut
from backend.modules.video_analysis.service import detector as detector_module
from backend.modules.video_analysis.service import pipeline as pipeline_module
from backend.modules.video_analysis.service.detector import YoloFrameDetector
from backend.modules.video_analysis.service.frame_extractor import iter_frames
from backend.modules.video_analysis.service.pipeline import OfflineVideoAnalysisPipeline
from backend.modules.vision_models import training_api
from backend.modules.vision_models.application import VisionNotFound
from backend.modules.vision_models.training_api import artifact_media_type


def test_registered_model_rejects_mutated_file(tmp_path):
    weights = tmp_path / "registered.pt"
    weights.write_bytes(b"published weights")
    expected = hashlib.sha256(weights.read_bytes()).hexdigest()
    weights.write_bytes(b"mutated weights")

    with pytest.raises(ModelArtifactIntegrityError, match="checksum mismatch"):
        YoloFrameDetector(
            "registered",
            model_path=weights,
            expected_checksum=expected,
            device="cpu",
        )


def test_model_cache_key_separates_devices(tmp_path, monkeypatch):
    weights = tmp_path / "builtin.pt"
    weights.write_bytes(b"immutable weights")
    created: list[str] = []

    class FakeYolo:
        def __init__(self, path: str):
            created.append(path)

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = FakeYolo
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    detector_module._MODEL_CACHE.clear()

    cpu_first = YoloFrameDetector("model", model_path=weights, device="cpu")
    cpu_second = YoloFrameDetector("model", model_path=weights, device="cpu")
    cuda = YoloFrameDetector("model", model_path=weights, device="cuda:0")

    assert cpu_first.model is cpu_second.model
    assert cpu_first.model is not cuda.model
    assert len(created) == 2


def _write_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (32, 24),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG writer is unavailable")
    for index in range(10):
        writer.write(np.full((24, 32, 3), index * 10, dtype=np.uint8))
    writer.release()


def test_decode_stride_gate_preserves_sample_indices_and_timestamps(tmp_path):
    video = tmp_path / "stride.avi"
    _write_synthetic_video(video)

    baseline = list(iter_frames(video, every_seconds=0.3))
    optimized = list(
        iter_frames(video, every_seconds=0.3, decode_stride_enabled=True)
    )

    assert [frame.frame_index for frame in baseline] == [0, 3, 6, 9]
    assert [frame.frame_index for frame in optimized] == [0, 3, 6, 9]
    assert [frame.timestamp_seconds for frame in optimized] == [
        frame.timestamp_seconds for frame in baseline
    ]


@pytest.mark.asyncio
async def test_standard_detector_batches_are_bounded(monkeypatch):
    async def frames(*_args, **_kwargs):
        for index in range(5):
            yield SimpleNamespace(
                frame_index=index,
                timestamp_seconds=float(index),
                image_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
            )

    async def inline(function, *args, **kwargs):
        ignored = {"boundary", "operation", "timeout_s"}
        return function(
            *args,
            **{key: value for key, value in kwargs.items() if key not in ignored},
        )

    batch_sizes: list[int] = []

    class Detector:
        def predict_batch(self, images):
            batch_sizes.append(len(images))
            return [[] for _ in images]

    monkeypatch.setattr(
        "backend.modules.video_analysis.service.inference_prefetch._decode_source",
        frames,
    )
    monkeypatch.setattr(pipeline_module, "run_blocking", inline)
    monkeypatch.setattr(
        pipeline_module.settings,
        "video_analysis_inference_batch_size",
        2,
    )
    pipeline = OfflineVideoAnalysisPipeline(SimpleNamespace())

    outputs = [
        item
        async for item in pipeline._iter_inference_frames(
            Path("video.mp4"),
            every_seconds=1.0,
            decode_stride_enabled=False,
            decoder_mode="opencv_sequential",
            detector=Detector(),
            allow_batching=True,
        )
    ]

    assert batch_sizes == [2, 2, 1]
    assert len(outputs) == 5
    assert all(item[1] == [] and item[2] is None for item in outputs)


def test_loaded_hash_round_trips_in_evidence_provenance():
    loaded_hash = "a" * 64
    detection = SimpleNamespace(
        id="detection-1",
        job_id="job-1",
        video_id="video-1",
        mission_id=None,
        frame_index=4,
        timestamp_seconds=0.4,
        label="crop",
        confidence=0.9,
        x1=1.0,
        y1=2.0,
        x2=3.0,
        y2=4.0,
        track_id=None,
        lat=None,
        lon=None,
        altitude_m=None,
        heading_deg=None,
        raw={"model_version": "registered:v1", "loaded_model_hash": loaded_hash},
        storage_object=SimpleNamespace(
            id="storage-1",
            state="final",
            checksum="b" * 64,
        ),
    )

    output = VideoDetectionOut.model_validate(detection)

    assert output.evidence is not None
    assert output.evidence.provenance["loaded_model_hash"] == loaded_hash


@pytest.mark.parametrize(
    ("content", "suffix", "expected"),
    [
        (b"\xff\xd8\xff\xe0jpeg", ".jpg", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\npng", ".png", "image/png"),
    ],
)
def test_evaluation_artifact_media_type_uses_bytes(
    tmp_path, content, suffix, expected
):
    artifact = tmp_path / f"artifact{suffix}"
    artifact.write_bytes(content)
    assert artifact_media_type(artifact) == expected


@pytest.mark.asyncio
async def test_vision_not_found_uses_versioned_envelope(monkeypatch):
    async def missing(*_args, **_kwargs):
        raise VisionNotFound("Model version not found")

    monkeypatch.setattr(training_api.application, "get_evaluation", missing)
    with pytest.raises(Exception) as raised:
        await training_api.get_evaluation(
            "missing",
            db=SimpleNamespace(),
            org_user=SimpleNamespace(user=SimpleNamespace()),
        )

    request = Request({"type": "http", "method": "GET", "path": "/"})
    response = await domain_api_error_handler(request, raised.value)
    assert response.status_code == 404
    assert b'"code":"VISION_NOT_FOUND"' in response.body
    assert b'"retryable":false' in response.body
