"""Video decoder benchmark modes (TASK 3.1).

These helpers mirror production sampling semantics from ``media_frames`` but stay
outside the runtime decode path. Production code is not modified by this module.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

MODE_OPENCV_SEQUENTIAL = "opencv_sequential"
MODE_OPENCV_SEEK = "opencv_seek"
MODE_PYAV_SEQUENTIAL = "pyav_sequential"
MODE_FFMPEG_PIPE = "ffmpeg_pipe"

ALL_MODES = (
    MODE_OPENCV_SEQUENTIAL,
    MODE_OPENCV_SEEK,
    MODE_PYAV_SEQUENTIAL,
    MODE_FFMPEG_PIPE,
)


@dataclass(frozen=True)
class VideoMetadata:
    fps: float
    width: int
    height: int
    frame_count: int
    duration_seconds: float


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


@dataclass(frozen=True)
class DecodeBenchmarkResult:
    decoded_frames: int
    selected_frames: int
    timestamp_error_max_seconds: float
    wall_time_seconds: float
    cpu_time_seconds: float
    ram_peak_mb: float | None
    available: bool
    error: str | None = None


def sample_rate_to_every_seconds(sample_rate_fps: float, fps: float) -> float:
    if sample_rate_fps <= 0:
        raise ValueError("sample_rate_fps must be > 0")
    return 1.0 / sample_rate_fps


def source_video_minutes_per_wall_minute(
    *,
    duration_seconds: float,
    wall_time_seconds: float,
) -> float | None:
    if wall_time_seconds <= 0:
        return None
    return (duration_seconds / 60.0) / (wall_time_seconds / 60.0)


def _run_timed(
    fn: Callable[[], tuple[int, int, float]],
    *,
    sample_ram: Callable[[], float | None],
) -> DecodeBenchmarkResult:
    ram_peak = 0.0
    ram_samples: list[float] = []

    def _sample() -> None:
        value = sample_ram()
        if value is not None:
            ram_samples.append(value)

    _sample()
    wall_start = time.monotonic()
    cpu_start = time.process_time()
    try:
        decoded, selected, timestamp_error = fn()
    except Exception as exc:
        return DecodeBenchmarkResult(
            decoded_frames=0,
            selected_frames=0,
            timestamp_error_max_seconds=0.0,
            wall_time_seconds=time.monotonic() - wall_start,
            cpu_time_seconds=time.process_time() - cpu_start,
            ram_peak_mb=max(ram_samples) if ram_samples else None,
            available=False,
            error=str(exc),
        )
    _sample()
    return DecodeBenchmarkResult(
        decoded_frames=decoded,
        selected_frames=selected,
        timestamp_error_max_seconds=timestamp_error,
        wall_time_seconds=time.monotonic() - wall_start,
        cpu_time_seconds=time.process_time() - cpu_start,
        ram_peak_mb=max(ram_samples) if ram_samples else None,
        available=True,
    )


def _opencv_sequential(
    video_path: Path,
    *,
    every_seconds: float,
) -> tuple[int, int, float]:
    metadata = read_video_metadata(video_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    fps = metadata.fps or 30.0
    stride_frames = max(1, round(fps * every_seconds))
    decoded = 0
    selected = 0
    frame_index = 0
    try:
        while True:
            ok, _frame = capture.read()
            if not ok:
                break
            decoded += 1
            if frame_index % stride_frames == 0:
                selected += 1
            frame_index += 1
    finally:
        capture.release()
    return decoded, selected, 0.0


def _opencv_seek(
    video_path: Path,
    *,
    every_seconds: float,
) -> tuple[int, int, float]:
    metadata = read_video_metadata(video_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    fps = metadata.fps or 30.0
    timestamp_error = 0.0
    decoded = 0
    selected = 0
    try:
        for frame_index in sampled_frame_indices(
            frame_count=metadata.frame_count,
            fps=fps,
            every_seconds=every_seconds,
        ):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, _frame = capture.read()
            if not ok:
                break
            decoded += 1
            selected += 1
            expected = frame_timestamp_seconds(frame_index, fps)
            actual_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
            timestamp_error = max(timestamp_error, abs(expected - actual_ms))
    finally:
        capture.release()
    return decoded, selected, timestamp_error


def _pyav_sequential(
    video_path: Path,
    *,
    every_seconds: float,
) -> tuple[int, int, float]:
    try:
        import av
    except ImportError as exc:
        raise RuntimeError("PyAV is not installed") from exc

    metadata = read_video_metadata(video_path)
    fps = metadata.fps or 30.0
    stride_frames = max(1, round(fps * every_seconds))
    decoded = 0
    selected = 0
    timestamp_error = 0.0
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            decoded += 1
            frame_index = decoded - 1
            if frame_index % stride_frames != 0:
                continue
            selected += 1
            expected = frame_timestamp_seconds(frame_index, fps)
            if frame.pts is not None and stream.time_base:
                actual = float(frame.pts * stream.time_base)
                timestamp_error = max(timestamp_error, abs(expected - actual))
    return decoded, selected, timestamp_error


def _ffmpeg_pipe(
    video_path: Path,
    *,
    every_seconds: float,
) -> tuple[int, int, float]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg binary not found on PATH")
    metadata = read_video_metadata(video_path)
    sample_fps = 1.0 / every_seconds
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={sample_fps}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "pipe:1",
    ]
    completed = subprocess.run(cmd, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or "ffmpeg decode failed")
    frame_bytes = metadata.width * metadata.height * 3
    if frame_bytes <= 0:
        raise ValueError("Invalid video dimensions for ffmpeg pipe decode")
    selected = len(completed.stdout) // frame_bytes
    decoded = metadata.frame_count or selected
    return decoded, selected, 0.0


_MODE_RUNNERS: dict[str, Callable[[Path, float], tuple[int, int, float]]] = {
    MODE_OPENCV_SEQUENTIAL: lambda path, every: _opencv_sequential(
        path, every_seconds=every
    ),
    MODE_OPENCV_SEEK: lambda path, every: _opencv_seek(path, every_seconds=every),
    MODE_PYAV_SEQUENTIAL: lambda path, every: _pyav_sequential(
        path, every_seconds=every
    ),
    MODE_FFMPEG_PIPE: lambda path, every: _ffmpeg_pipe(path, every_seconds=every),
}


def benchmark_decoder_mode(
    mode: str,
    video_path: Path,
    *,
    sample_rate_fps: float,
    sample_ram: Callable[[], float | None],
) -> DecodeBenchmarkResult:
    if mode not in _MODE_RUNNERS:
        raise ValueError(f"Unknown decoder mode: {mode}")
    metadata = read_video_metadata(video_path)
    every_seconds = sample_rate_to_every_seconds(sample_rate_fps, metadata.fps or 30.0)
    runner = _MODE_RUNNERS[mode]
    return _run_timed(lambda: runner(video_path, every_seconds), sample_ram=sample_ram)


def write_synthetic_video(
    path: Path,
    *,
    fps: float = 30.0,
    frame_count: int = 300,
    width: int = 1920,
    height: int = 1080,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not create synthetic video: {path}")
    rng = np.random.default_rng(0)
    try:
        for index in range(frame_count):
            frame = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
            frame[:, :, 0] = index % 255
            writer.write(frame)
    finally:
        writer.release()
