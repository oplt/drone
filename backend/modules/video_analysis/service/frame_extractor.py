from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


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


def read_video_metadata(video_path: str | Path) -> VideoMetadata:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    capture.release()

    return VideoMetadata(
        fps=fps,
        width=width,
        height=height,
        frame_count=frame_count,
        duration_seconds=duration,
    )


def iter_frames(
    video_path: str | Path,
    *,
    every_seconds: float = 1.0,
) -> Iterator[ExtractedFrame]:
    """Yield BGR frames at a fixed temporal stride.

    For offline analysis this is usually better than processing every frame.
    For example, every_seconds=1.0 means 1 inference frame per second.
    """
    if every_seconds <= 0:
        raise ValueError("every_seconds must be > 0")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    stride_frames = max(1, round(fps * every_seconds))

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    try:
        # For sparse analysis, seek directly to sampled frames instead of decoding all frames.
        if stride_frames >= max(8, int(fps / 2)) and frame_count > 0:
            for frame_index in range(0, frame_count, stride_frames):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok:
                    break
                yield ExtractedFrame(frame_index, frame_index / fps, frame)
            return

        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride_frames == 0:
                yield ExtractedFrame(frame_index, frame_index / fps, frame)
            frame_index += 1
    finally:
        capture.release()
