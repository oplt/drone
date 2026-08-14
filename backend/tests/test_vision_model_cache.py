from __future__ import annotations

import hashlib
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from backend.core.config.runtime import default_video_analysis_inference_batch_size
from backend.modules.patrol.vision.detector import ObjectDetector
from backend.modules.patrol.vision.models import FramePacket
from backend.modules.video_analysis.service import detector as detector_module
from backend.modules.video_analysis.service.detector import YoloFrameDetector, load_yolo_model


def test_default_inference_batch_size_is_one_without_cuda(monkeypatch) -> None:
    torch = ModuleType("torch")
    torch.cuda = ModuleType("cuda")
    torch.cuda.is_available = lambda: False
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert default_video_analysis_inference_batch_size() == 1


def test_default_inference_batch_size_is_eight_with_cuda(monkeypatch) -> None:
    torch = ModuleType("torch")
    torch.cuda = ModuleType("cuda")
    torch.cuda.is_available = lambda: True
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert default_video_analysis_inference_batch_size() == 8


def test_concurrent_yolo_load_uses_singleflight(tmp_path, monkeypatch) -> None:
    weights = tmp_path / "shared.pt"
    weights.write_bytes(b"shared weights")
    created_count = 0
    create_lock = threading.Lock()

    class FakeYolo:
        def __init__(self, path: str):
            nonlocal created_count
            with create_lock:
                created_count += 1
            self.path = path

        def predict(self, **_kwargs):
            return []

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = FakeYolo
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    detector_module._MODEL_CACHE.clear()
    detector_module._MODEL_LOAD_WAITERS.clear()

    artifact_hash = "a" * 64
    errors: list[BaseException] = []

    def _load() -> None:
        try:
            load_yolo_model(str(weights), artifact_hash=artifact_hash, device="cpu")
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=_load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)
        assert not thread.is_alive()

    assert errors == []
    assert created_count == 1


def test_model_cache_lru_evicts_oldest_entries(tmp_path, monkeypatch) -> None:
    created: list[str] = []

    class FakeYolo:
        def __init__(self, path: str):
            created.append(path)

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = FakeYolo
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    detector_module._MODEL_CACHE.clear()
    detector_module._MODEL_LOAD_WAITERS.clear()
    original_max = detector_module._MODEL_CACHE_MAX
    detector_module._MODEL_CACHE_MAX = 2
    try:
        first = load_yolo_model(str(tmp_path / "one.pt"), artifact_hash="1" * 64, device="cpu")
        second = load_yolo_model(str(tmp_path / "two.pt"), artifact_hash="2" * 64, device="cpu")
        third = load_yolo_model(str(tmp_path / "three.pt"), artifact_hash="3" * 64, device="cpu")
    finally:
        detector_module._MODEL_CACHE_MAX = original_max

    assert len(created) == 3
    assert first is not third
    assert second is third or first is not second
    assert len(detector_module._MODEL_CACHE) == 2


def test_patrol_detector_reuses_video_analysis_model_cache(tmp_path, monkeypatch) -> None:
    weights = tmp_path / "yolo26n.pt"
    weights.write_bytes(b"builtin weights")
    artifact_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    created: list[str] = []

    class FakeYolo:
        def __init__(self, path: str):
            created.append(path)

        def predict(self, **_kwargs):
            box = ModuleType("box")
            box.cls = [ModuleType("cls")]
            box.cls[0].item = lambda: 0
            box.conf = [ModuleType("conf")]
            box.conf[0].item = lambda: 0.95
            box.xyxy = [ModuleType("xyxy")]
            box.xyxy[0].tolist = lambda: [1, 2, 3, 4]
            result = ModuleType("result")
            result.names = {0: "person"}
            result.boxes = [box]
            return [result]

    ultralytics = ModuleType("ultralytics")
    ultralytics.YOLO = FakeYolo
    torch = ModuleType("torch")
    torch.inference_mode = lambda: _InferenceContext()
    torch.cuda = ModuleType("cuda")
    torch.cuda.is_available = lambda: False
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setattr(
        "backend.modules.patrol.vision.detector.ensure_model_file",
        lambda _name: weights,
    )
    monkeypatch.setattr(
        "backend.modules.patrol.vision.detector.resolve_model_artifact",
        lambda _name, *, model_path, expected_checksum=None: type(
            "Artifact",
            (),
            {"path": Path(model_path), "artifact_hash": artifact_hash},
        )(),
    )
    detector_module._MODEL_CACHE.clear()
    detector_module._MODEL_LOAD_WAITERS.clear()

    video_detector = YoloFrameDetector("yolo26n.pt", model_path=weights, device="cpu")
    patrol_detector = ObjectDetector("yolo26n.pt")
    patrol_detector.detect(
        FramePacket(
            image=np.zeros((8, 8, 3), dtype=np.uint8),
            ts=datetime.now(UTC),
            frame_id=1,
        )
    )

    assert len(created) == 1
    assert patrol_detector._model is video_detector.model


class _InferenceContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False
