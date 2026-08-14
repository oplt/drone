from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

_SENTINEL = object()


def resolve_inference_prefetch_size(
    *,
    batch_size: int,
    configured: int | None,
) -> int:
    if configured is not None:
        return max(1, int(configured))
    return max(2, min(max(1, batch_size) * 2, 8))


def _record_queue_depth(
    stage_timings: dict[str, float] | None,
    *,
    depth: int,
    waited_ms: float,
) -> None:
    if stage_timings is None:
        return
    stage_timings["prefetch_queue_wait_ms"] = stage_timings.get(
        "prefetch_queue_wait_ms", 0.0
    ) + waited_ms
    stage_timings["prefetch_queue_depth_max"] = max(
        float(stage_timings.get("prefetch_queue_depth_max", 0.0)),
        float(depth),
    )


async def _queue_get(
    queue: asyncio.Queue[object],
    *,
    stage_timings: dict[str, float] | None,
) -> object:
    if queue.qsize() == 0:
        waited = time.monotonic()
        item = await queue.get()
        _record_queue_depth(
            stage_timings,
            depth=queue.qsize(),
            waited_ms=(time.monotonic() - waited) * 1000.0,
        )
        return item
    item = queue.get_nowait()
    _record_queue_depth(stage_timings, depth=queue.qsize(), waited_ms=0.0)
    return item


async def _run_inference_batch(
    frames: list[Any],
    predict_batch,
) -> AsyncIterator[tuple[Any, list[Any] | None, Exception | None, float]]:
    from backend.infrastructure.runtime.blocking import run_blocking

    started = time.monotonic()
    try:
        results = await run_blocking(
            predict_batch,
            [frame.image_bgr for frame in frames],
            boundary="cpu",
            operation="video_inference_batch",
            timeout_s=120.0,
        )
        if len(results) != len(frames):
            raise RuntimeError("Detector batch returned an unexpected result count.")
        per_frame_latency_ms = (time.monotonic() - started) * 1000.0 / len(frames)
        for frame, detections in zip(frames, results, strict=True):
            yield frame, detections, None, per_frame_latency_ms
    except Exception as exc:
        per_frame_latency_ms = (time.monotonic() - started) * 1000.0 / len(frames)
        for frame in frames:
            yield frame, None, exc, per_frame_latency_ms


async def _run_single_inference(
    frame: Any,
    predict,
) -> tuple[Any, list[Any] | None, Exception | None, float]:
    from backend.infrastructure.runtime.blocking import run_blocking

    started = time.monotonic()
    try:
        detections = await run_blocking(
            predict,
            frame.image_bgr,
            boundary="cpu",
            operation="video_inference",
            timeout_s=120.0,
        )
        latency_ms = (time.monotonic() - started) * 1000.0
        return frame, detections, None, latency_ms
    except Exception as exc:
        latency_ms = (time.monotonic() - started) * 1000.0
        return frame, None, exc, latency_ms


async def _decode_source(
    video_path: Path,
    *,
    every_seconds: float,
    decode_stride_enabled: bool,
    decoder_mode: str,
    stage_timings: dict[str, float] | None,
):
    from backend.modules.video_analysis.service.frame_extractor import async_iter_frames

    async for frame in async_iter_frames(
        video_path,
        every_seconds=every_seconds,
        decode_stride_enabled=decode_stride_enabled,
        decoder_mode=decoder_mode,
        stage_timings=stage_timings,
    ):
        yield frame


async def async_iter_prefetched_inference(
    video_path: Path,
    *,
    every_seconds: float,
    decode_stride_enabled: bool,
    decoder_mode: str,
    detector: Any,
    batch_size: int,
    prefetch_size: int,
    allow_batching: bool,
    stage_timings: dict[str, float] | None = None,
) -> AsyncIterator[tuple[Any, list[Any] | None, Exception | None, float]]:
    """Decode frames into a bounded queue while GPU inference consumes batches."""
    from contextlib import suppress

    bounded_prefetch = max(1, int(prefetch_size))
    queue: asyncio.Queue[object] = asyncio.Queue(maxsize=bounded_prefetch)
    predict_batch = getattr(detector, "predict_batch", None)
    use_batching = (
        batch_size > 1 and allow_batching and predict_batch is not None
    )

    async def _fill_queue() -> None:
        try:
            async for frame in _decode_source(
                video_path,
                every_seconds=every_seconds,
                decode_stride_enabled=decode_stride_enabled,
                decoder_mode=decoder_mode,
                stage_timings=stage_timings,
            ):
                await queue.put(frame)
                _record_queue_depth(stage_timings, depth=queue.qsize(), waited_ms=0.0)
            await queue.put(_SENTINEL)
        except Exception as exc:
            await queue.put(exc)
            await queue.put(_SENTINEL)

    filler = asyncio.create_task(_fill_queue())
    try:
        if not use_batching:
            predict = detector.predict
            while True:
                item = await _queue_get(queue, stage_timings=stage_timings)
                if isinstance(item, Exception):
                    raise item
                if item is _SENTINEL:
                    return
                yield await _run_single_inference(item, predict)
            return

        pending: list[Any] = []
        while True:
            item = await _queue_get(queue, stage_timings=stage_timings)
            if isinstance(item, Exception):
                raise item
            if item is _SENTINEL:
                if pending:
                    async for result in _run_inference_batch(pending, predict_batch):
                        yield result
                return
            pending.append(item)
            if len(pending) >= batch_size:
                async for result in _run_inference_batch(pending, predict_batch):
                    yield result
                pending = []
    finally:
        filler.cancel()
        with suppress(asyncio.CancelledError):
            await filler
