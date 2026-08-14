from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PREFETCH_MODULE = (
    REPO_ROOT / "backend/modules/video_analysis/service/inference_prefetch.py"
)


def _load_prefetch_module():
    spec = importlib.util.spec_from_file_location(
        "video_inference_prefetch",
        PREFETCH_MODULE,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_inference_prefetch_size_defaults_from_batch() -> None:
    module = _load_prefetch_module()
    assert module.resolve_inference_prefetch_size(batch_size=1, configured=None) == 2
    assert module.resolve_inference_prefetch_size(batch_size=4, configured=None) == 8
    assert module.resolve_inference_prefetch_size(batch_size=8, configured=None) == 8
    assert module.resolve_inference_prefetch_size(batch_size=4, configured=3) == 3


def test_prefetch_pipeline_batches_with_bounded_queue(monkeypatch) -> None:
    async def _run() -> None:
        module = _load_prefetch_module()
        max_depth = 0
        frames = [
            SimpleNamespace(
                frame_index=index,
                timestamp_seconds=float(index),
                image_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
            )
            for index in range(5)
        ]

        async def fake_async_iter_frames(*_args, **_kwargs):
            for frame in frames:
                yield frame
                await asyncio.sleep(0)

        monkeypatch.setattr(module, "_decode_source", fake_async_iter_frames)

        original_queue = module.asyncio.Queue

        class TrackingQueue(original_queue):
            async def put(self, item) -> None:  # type: ignore[override]
                nonlocal max_depth
                await super().put(item)
                max_depth = max(max_depth, self.qsize())

        monkeypatch.setattr(module.asyncio, "Queue", TrackingQueue)

        batch_sizes: list[int] = []

        class Detector:
            def predict_batch(self, images):
                batch_sizes.append(len(images))
                return [[] for _ in images]

        async def inline_batch(frames, predict_batch):
            started = module.time.monotonic()
            results = predict_batch([frame.image_bgr for frame in frames])
            per_frame_latency_ms = (module.time.monotonic() - started) * 1000.0 / len(
                frames
            )
            for frame, detections in zip(frames, results, strict=True):
                yield frame, detections, None, per_frame_latency_ms

        monkeypatch.setattr(module, "_run_inference_batch", inline_batch)

        outputs = [
            item
            async for item in module.async_iter_prefetched_inference(
                "video.mp4",
                every_seconds=1.0,
                decode_stride_enabled=False,
                decoder_mode="opencv_sequential",
                detector=Detector(),
                batch_size=2,
                prefetch_size=2,
                allow_batching=True,
                stage_timings={},
            )
        ]

        assert batch_sizes == [2, 2, 1]
        assert len(outputs) == 5
        assert max_depth <= 2

    asyncio.run(_run())


def test_prefetch_pipeline_runs_single_frame_inference(monkeypatch) -> None:
    async def _run() -> None:
        module = _load_prefetch_module()
        frame = SimpleNamespace(
            frame_index=0,
            timestamp_seconds=0.0,
            image_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        )

        async def fake_async_iter_frames(*_args, **_kwargs):
            yield frame

        async def inline_single(frame, predict):
            return frame, predict(frame.image_bgr), None, 0.0

        monkeypatch.setattr(module, "_decode_source", fake_async_iter_frames)
        monkeypatch.setattr(module, "_run_single_inference", inline_single)

        class Detector:
            def predict(self, _image):
                return [{"label": "crop"}]

        frame_out, detections, error, latency = await anext(
            module.async_iter_prefetched_inference(
                "video.mp4",
                every_seconds=1.0,
                decode_stride_enabled=False,
                decoder_mode="opencv_sequential",
                detector=Detector(),
                batch_size=1,
                prefetch_size=2,
                allow_batching=False,
                stage_timings={},
            )
        )

        assert frame_out is frame
        assert detections == [{"label": "crop"}]
        assert error is None
        assert latency >= 0.0

    asyncio.run(_run())


def test_prefetch_stops_when_consumer_exits(monkeypatch) -> None:
    async def _run() -> None:
        module = _load_prefetch_module()
        started = False

        async def fake_async_iter_frames(*_args, **_kwargs):
            nonlocal started
            started = True
            for index in range(100):
                yield SimpleNamespace(
                    frame_index=index,
                    timestamp_seconds=float(index),
                    image_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
                )
                await asyncio.sleep(0.01)

        monkeypatch.setattr(module, "_decode_source", fake_async_iter_frames)

        async def inline_single(frame, predict):
            return frame, predict(frame.image_bgr), None, 0.0

        monkeypatch.setattr(module, "_run_single_inference", inline_single)

        class Detector:
            def predict(self, _image):
                return []

        generator = module.async_iter_prefetched_inference(
            "video.mp4",
            every_seconds=1.0,
            decode_stride_enabled=False,
            decoder_mode="opencv_sequential",
            detector=Detector(),
            batch_size=1,
            prefetch_size=2,
            allow_batching=False,
            stage_timings={},
        )
        await anext(generator)
        await generator.aclose()
        await asyncio.sleep(0.05)
        assert started is True

    asyncio.run(_run())
