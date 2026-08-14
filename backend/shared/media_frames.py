from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.infrastructure.runtime.blocking import run_blocking

MAX_FRAME_BUFFER = 2


@dataclass(frozen=True)
class VideoMetadata:
    fps: float
    width: int
    height: int
    frame_count: int
    duration_seconds: float


@dataclass(frozen=True)
class ExtractedFrame:
    frame_index: int
    timestamp_seconds: float
    image_bgr: np.ndarray


def sampled_frame_indices(
    *, frame_count: int, fps: float, every_seconds: float
) -> range:
    if every_seconds <= 0:
        raise ValueError("every_seconds must be > 0")
    stride_frames = max(1, round(fps * every_seconds))
    return range(0, max(0, frame_count), stride_frames)


def frame_timestamp_seconds(frame_index: int, fps: float) -> float:
    return frame_index / fps


def read_video_metadata(video_path: str | Path) -> VideoMetadata:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()
    return VideoMetadata(
        fps=fps,
        width=width,
        height=height,
        frame_count=frame_count,
        duration_seconds=frame_count / fps if fps > 0 else 0.0,
    )


async def read_video_metadata_async(video_path: str | Path) -> VideoMetadata:
    return await run_blocking(
        read_video_metadata,
        video_path,
        boundary="media",
        operation="read_video_metadata",
        timeout_s=30.0,
    )


def iter_frames(
    video_path: str | Path,
    *,
    every_seconds: float = 1.0,
    decode_stride_enabled: bool = False,
) -> Iterator[ExtractedFrame]:
    if every_seconds <= 0:
        raise ValueError("every_seconds must be > 0")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride_frames = max(1, round(fps * every_seconds))
    try:
        if decode_stride_enabled and frame_count > 0:
            for frame_index in sampled_frame_indices(
                frame_count=frame_count,
                fps=fps,
                every_seconds=every_seconds,
            ):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok:
                    break
                yield ExtractedFrame(
                    frame_index,
                    frame_timestamp_seconds(frame_index, fps),
                    frame,
                )
            return
        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride_frames == 0:
                yield ExtractedFrame(
                    frame_index,
                    frame_timestamp_seconds(frame_index, fps),
                    frame,
                )
            frame_index += 1
    finally:
        capture.release()


def _next_frame_or_none(iterator: Iterator[ExtractedFrame]) -> ExtractedFrame | None:
    return next(iterator, None)


async def async_iter_frames(
    video_path: str | Path,
    *,
    every_seconds: float = 1.0,
    decode_stride_enabled: bool = False,
) -> AsyncIterator[ExtractedFrame]:
    iterator = iter_frames(
        video_path,
        every_seconds=every_seconds,
        decode_stride_enabled=decode_stride_enabled,
    )
    queue: asyncio.Queue[object] = asyncio.Queue(maxsize=MAX_FRAME_BUFFER)

    async def _decode() -> None:
        try:
            while True:
                frame = await run_blocking(
                    _next_frame_or_none,
                    iterator,
                    boundary="media",
                    operation="decode_video_frame",
                    timeout_s=30.0,
                )
                await queue.put(frame)
                if frame is None:
                    return
        except Exception as exc:
            await queue.put(exc)
            await queue.put(None)

    producer = asyncio.create_task(_decode())
    try:
        while True:
            item = await queue.get()
            if isinstance(item, Exception):
                raise item
            if item is None:
                return
            yield item
    finally:
        producer.cancel()
        with suppress(asyncio.CancelledError):
            await producer
