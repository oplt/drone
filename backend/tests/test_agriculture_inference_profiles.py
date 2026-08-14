from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.core.config.runtime import settings
from backend.modules.agriculture import service as agriculture_service_module
from backend.modules.agriculture.capabilities import CAPABILITIES
from backend.modules.agriculture.inference_profiles import (
    PROFILE_SCHEMA_VERSION,
    default_inference_profile,
    resolve_inference_profile,
    video_request_for_profile,
)
from backend.modules.agriculture.service import AgricultureService
from backend.modules.video_analysis.schemas import AnalyzeVideoRequest
from backend.modules.video_analysis.service import pipeline as pipeline_module
from backend.modules.video_analysis.service.detector import YoloFrameDetector
from backend.modules.video_analysis.service.inference_profile_runtime import (
    detector_options,
    precision_predict_options,
    resolve_inference_batch_size,
    resolve_precision_mode,
    resolve_sahi_enabled,
)
from backend.modules.video_analysis.service.pipeline import OfflineVideoAnalysisPipeline


def test_every_model_capability_has_a_complete_versioned_profile() -> None:
    model_capabilities = {item.id for item in CAPABILITIES.values() if item.requires_model}
    profiles = {
        capability_id: default_inference_profile(capability_id)
        for capability_id in model_capabilities
    }

    assert {profile["capability_id"] for profile in profiles.values()} == model_capabilities
    assert len({profile["profile_id"] for profile in profiles.values()}) == len(profiles)
    for profile in profiles.values():
        assert profile["profile_version"] == PROFILE_SCHEMA_VERSION
        assert profile["sample_fps"] == 1.0
        assert profile["image_size"] == 640
        assert profile["confidence_threshold"] == 0.35
        assert profile["batch_size"] == settings.video_analysis_inference_batch_size
        assert profile["precision_mode"] == "fp32"
        assert profile["sahi_enabled"] is False
        assert profile["sahi_slice_height"] == 640
        assert profile["sahi_slice_width"] == 640
        assert len(profile["profile_digest"]) == 64


def test_profile_digest_is_stable_and_covers_identity_and_execution_values() -> None:
    baseline = default_inference_profile("weed_detection")
    assert resolve_inference_profile("weed_detection", baseline) == baseline

    changed = deepcopy(baseline)
    changed["confidence_threshold"] = 0.5
    assert (
        resolve_inference_profile("weed_detection", changed)["profile_digest"]
        != baseline["profile_digest"]
    )

    changed = deepcopy(baseline)
    changed["profile_version"] = "agriculture-inference-profile.v2"
    assert (
        resolve_inference_profile("weed_detection", changed)["profile_digest"]
        != baseline["profile_digest"]
    )


def test_legacy_release_profile_is_normalized_without_changing_behavior() -> None:
    profile = resolve_inference_profile(
        "stand_count",
        {
            "frame_stride_seconds": 0.5,
            "confidence_threshold": 0.6,
            "small_object_mode": True,
            "tracking_enabled": False,
            "tracker_type": "bytetrack",
        },
    )

    assert profile["sample_fps"] == 2.0
    assert profile["confidence_threshold"] == 0.6
    assert profile["sahi_enabled"] is True


def test_profile_validation_rejects_invalid_or_cross_capability_values() -> None:
    with pytest.raises(ValidationError, match="multiples of 32"):
        resolve_inference_profile("stand_count", {"image_size": 641})
    with pytest.raises(ValueError, match="does not match"):
        resolve_inference_profile("stand_count", {"capability_id": "weed_detection"})
    with pytest.raises(ValueError, match="greater than zero"):
        resolve_inference_profile("stand_count", {"frame_stride_seconds": 0})

    profile = default_inference_profile("stand_count")
    with pytest.raises(ValidationError, match="digest does not match"):
        AnalyzeVideoRequest(inference_profile={**profile, "profile_digest": "0" * 64})
    with pytest.raises(ValidationError, match="FP16 with SAHI"):
        resolve_inference_profile("stand_count", {"precision_mode": "fp16", "sahi_enabled": True})


def test_profile_builds_a_consistent_video_request() -> None:
    profile = resolve_inference_profile(
        "standing_water",
        {
            "sample_fps": 2.0,
            "image_size": 960,
            "confidence_threshold": 0.4,
            "batch_size": 2,
            "sahi_enabled": True,
            "sahi_slice_height": 320,
            "sahi_slice_width": 384,
        },
    )

    request = video_request_for_profile(
        capability_id="standing_water",
        model_version_id="version-1",
        profile=profile,
    )

    assert request.frame_stride_seconds == 0.5
    assert request.confidence_threshold == 0.4
    assert request.small_object_mode is True
    assert request.inference_profile is not None
    assert request.inference_profile.model_dump() == profile
    with pytest.raises(ValidationError, match="conflicts"):
        AnalyzeVideoRequest(
            frame_stride_seconds=1.0,
            confidence_threshold=0.4,
            small_object_mode=True,
            inference_profile=request.inference_profile,
        )


@pytest.mark.asyncio
async def test_analysis_fingerprint_records_profile_identity(monkeypatch) -> None:
    class Database:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value: object) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            return None

        async def refresh(self, _value: object) -> None:
            return None

    monkeypatch.setattr(
        agriculture_service_module.agriculture_repository,
        "get_run_by_key",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        agriculture_service_module, "emit_agriculture_event", lambda *_args, **_kwargs: None
    )
    flight = SimpleNamespace(id="flight-1", input_manifest={"source_checksum": "source"})
    baseline = default_inference_profile("weed_detection")

    async def create(profile: dict[str, object], key: str):
        return await AgricultureService().create_analysis_run(
            Database(),
            flight=flight,
            values={
                "idempotency_key": key,
                "requested_analyses": ["weed_detection"],
                "analysis_profile": {},
                "model_versions": {"weed_detection": {"inference_profile": profile}},
                "calibration_versions": {},
                "parameters": {},
                "baseline_flight_id": None,
                "requested_by_user_id": 7,
            },
        )

    first = await create(baseline, "profile-fingerprint-1")
    changed = resolve_inference_profile("weed_detection", {**baseline, "profile_version": "v2"})
    second = await create(changed, "profile-fingerprint-2")

    recorded = first.input_manifest["model_versions"]["weed_detection"]
    assert recorded["inference_profile"]["profile_digest"] == baseline["profile_digest"]
    assert first.input_checksum != second.input_checksum


def test_runtime_resolves_profile_detector_and_batch_options() -> None:
    profile = resolve_inference_profile("crop_health", {"image_size": 960, "batch_size": 4})

    assert detector_options(profile)["image_size"] == 960
    assert resolve_inference_batch_size(profile, default=1) == 4
    assert resolve_inference_batch_size(None, default=8) == 8
    assert resolve_sahi_enabled(profile, legacy_enabled=False) is False
    with pytest.raises(RuntimeError, match="conflicts"):
        resolve_sahi_enabled(profile, legacy_enabled=True)


def test_fp16_is_explicit_and_requires_a_capable_cuda_device() -> None:
    assert resolve_precision_mode("fp32", device="cpu") == "fp32"
    assert precision_predict_options("fp32") == {}
    with pytest.raises(RuntimeError, match="CUDA device"):
        resolve_precision_mode("fp16", device="cpu")
    with pytest.raises(RuntimeError, match="CUDA is unavailable"):
        resolve_precision_mode("fp16", device="cuda:0", cuda_available=False, cuda_capability=None)
    with pytest.raises(RuntimeError, match="5.3"):
        resolve_precision_mode("fp16", device="cuda:0", cuda_available=True, cuda_capability=(5, 2))
    assert (
        resolve_precision_mode("fp16", device="cuda:0", cuda_available=True, cuda_capability=(7, 5))
        == "fp16"
    )
    assert precision_predict_options("fp16") == {"quantize": "fp16"}


@pytest.mark.asyncio
async def test_pipeline_uses_profile_batch_size(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def prefetched(*_args, **kwargs):
        captured.update(kwargs)
        if False:
            yield None

    monkeypatch.setattr(pipeline_module, "async_iter_prefetched_inference", prefetched)
    pipeline = OfflineVideoAnalysisPipeline(SimpleNamespace())
    profile = resolve_inference_profile("stand_count", {"batch_size": 4})

    output = [
        item
        async for item in pipeline._iter_inference_frames(
            Path("video.mp4"),
            every_seconds=1.0,
            decode_stride_enabled=False,
            decoder_mode="opencv_sequential",
            detector=SimpleNamespace(),
            allow_batching=True,
            inference_profile=profile,
        )
    ]

    assert output == []
    assert captured["batch_size"] == 4


def test_standard_detector_applies_profile_image_size() -> None:
    calls: list[dict[str, object]] = []

    class Model:
        def predict(self, **kwargs):
            calls.append(kwargs)
            return []

    detector = YoloFrameDetector.__new__(YoloFrameDetector)
    detector.model = Model()
    detector.confidence_threshold = 0.35
    detector.image_size = 960
    detector.precision_mode = "fp32"
    detector.device = "cpu"
    detector.model_name = "model"
    detector.loaded_model_hash = "a" * 64

    assert detector.predict_batch([object()]) == []
    assert calls[0]["imgsz"] == 960
    assert "quantize" not in calls[0]

    detector.precision_mode = "fp16"
    assert detector.predict_batch([object()]) == []
    assert calls[1]["quantize"] == "fp16"
