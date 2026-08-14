from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DECODER_OPENCV_SEQUENTIAL = "opencv_sequential"
DECODER_OPENCV_SEEK = "opencv_seek"
DECODER_PYAV_SEQUENTIAL = "pyav_sequential"
DECODER_FFMPEG_PIPE = "ffmpeg_pipe"

SUPPORTED_DECODERS = (
    DECODER_OPENCV_SEQUENTIAL,
    DECODER_OPENCV_SEEK,
    DECODER_PYAV_SEQUENTIAL,
    DECODER_FFMPEG_PIPE,
)

DEFAULT_DECODER = DECODER_OPENCV_SEQUENTIAL
TIMESTAMP_ERROR_THRESHOLD_SECONDS = 0.1


def resolve_effective_decoder(
    *,
    configured: str | None,
    decode_stride_enabled: bool,
) -> str:
    mode = (configured or DEFAULT_DECODER).strip().lower()
    if mode not in SUPPORTED_DECODERS:
        mode = DEFAULT_DECODER
    if decode_stride_enabled and mode == DECODER_OPENCV_SEQUENTIAL:
        return DECODER_OPENCV_SEEK
    return mode


def _media_frames():
    from backend.shared import media_frames

    return media_frames


def _should_fallback(from_mode: str, exc: Exception) -> bool:
    if from_mode == DEFAULT_DECODER:
        return False
    logger.warning(
        "Video decoder %s failed (%s); falling back to %s",
        from_mode,
        exc,
        DEFAULT_DECODER,
    )
    return True


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Video frame decode cancelled")


def _opencv_sequential(
    video_path: Path,
    *,
    every_seconds: float,
    cancel_event: threading.Event | None,
) -> Iterator[object]:
    media = _media_frames()
    metadata = media.read_video_metadata(video_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    fps = metadata.fps or 30.0
    stride_frames = max(1, round(fps * every_seconds))
    frame_index = 0
    try:
        while True:
            _check_cancelled(cancel_event)
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride_frames == 0:
                yield media.ExtractedFrame(
                    frame_index,
                    media.frame_timestamp_seconds(frame_index, fps),
                    frame,
                )
            frame_index += 1
    finally:
        capture.release()


def _opencv_seek(
    video_path: Path,
    *,
    every_seconds: float,
    cancel_event: threading.Event | None,
) -> Iterator[object]:
    media = _media_frames()
    metadata = media.read_video_metadata(video_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    fps = metadata.fps or 30.0
    try:
        for frame_index in media.sampled_frame_indices(
            frame_count=metadata.frame_count,
            fps=fps,
            every_seconds=every_seconds,
        ):
            _check_cancelled(cancel_event)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                break
            yield media.ExtractedFrame(
                frame_index,
                media.frame_timestamp_seconds(frame_index, fps),
                frame,
            )
    finally:
        capture.release()


def _pyav_sequential(
    video_path: Path,
    *,
    every_seconds: float,
    cancel_event: threading.Event | None,
) -> Iterator[object]:
    try:
        import av
    except ImportError as exc:
        raise RuntimeError("PyAV is not installed") from exc

    media = _media_frames()
    metadata = media.read_video_metadata(video_path)
    fps = metadata.fps or 30.0
    stride_frames = max(1, round(fps * every_seconds))
    decoded = 0
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            _check_cancelled(cancel_event)
            decoded += 1
            frame_index = decoded - 1
            if frame_index % stride_frames != 0:
                continue
            image = frame.to_ndarray(format="bgr24")
            yield media.ExtractedFrame(
                frame_index,
                media.frame_timestamp_seconds(frame_index, fps),
                image,
            )


def _ffmpeg_pipe(
    video_path: Path,
    *,
    every_seconds: float,
    cancel_event: threading.Event | None,
) -> Iterator[object]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg binary not found on PATH")

    media = _media_frames()
    metadata = media.read_video_metadata(video_path)
    if metadata.width <= 0 or metadata.height <= 0:
        raise ValueError("Invalid video dimensions for ffmpeg pipe decode")

    sample_fps = 1.0 / every_seconds
    frame_bytes = metadata.width * metadata.height * 3
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
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    fps = metadata.fps or 30.0
    stride_frames = max(1, round(fps * every_seconds))
    selected_index = 0
    try:
        while True:
            _check_cancelled(cancel_event)
            chunk = process.stdout.read(frame_bytes)
            if len(chunk) < frame_bytes:
                break
            frame_index = selected_index * stride_frames
            image = np.frombuffer(chunk, dtype=np.uint8).reshape(
                (metadata.height, metadata.width, 3)
            )
            yield media.ExtractedFrame(
                frame_index,
                media.frame_timestamp_seconds(frame_index, fps),
                image.copy(),
            )
            selected_index += 1
    finally:
        if cancel_event is not None and cancel_event.is_set():
            process.kill()
        else:
            process.terminate()
        process.wait(timeout=5)


_MODE_ITERATORS = {
    DECODER_OPENCV_SEQUENTIAL: _opencv_sequential,
    DECODER_OPENCV_SEEK: _opencv_seek,
    DECODER_PYAV_SEQUENTIAL: _pyav_sequential,
    DECODER_FFMPEG_PIPE: _ffmpeg_pipe,
}


def iter_frames_with_decoder(
    video_path: str | Path,
    *,
    every_seconds: float,
    decoder_mode: str,
    cancel_event: threading.Event | None = None,
) -> Iterator[object]:
    if every_seconds <= 0:
        raise ValueError("every_seconds must be > 0")
    path = Path(video_path)
    mode = resolve_effective_decoder(
        configured=decoder_mode,
        decode_stride_enabled=False,
    )
    try:
        yield from _MODE_ITERATORS[mode](
            path,
            every_seconds=every_seconds,
            cancel_event=cancel_event,
        )
    except Exception as exc:
        if not _should_fallback(mode, exc):
            raise
        yield from _MODE_ITERATORS[DEFAULT_DECODER](
            path,
            every_seconds=every_seconds,
            cancel_event=cancel_event,
        )
