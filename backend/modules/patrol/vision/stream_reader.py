from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol

import cv2
import numpy as np

from backend.core.config.runtime import settings
from backend.infrastructure.camera.stream_client import open_video_capture
from backend.modules.patrol.vision.models import FramePacket

# Reuse the survey-camera MJPEG worker instead of opening a second UDP/RTSP client.
SHARED_VIDEO_STREAM_SOURCE = "__shared_video_runtime__"


class FrameReader(Protocol):
    source: str | int

    def open(self) -> None: ...

    def close(self) -> None: ...

    def read(self) -> FramePacket | None: ...


def create_stream_reader(
    source: str | int,
    *,
    frame_stride: int = 1,
    reopen_delay_s: float = 0.2,
) -> FrameReader:
    if source == SHARED_VIDEO_STREAM_SOURCE:
        return SharedVideoStreamReader(
            frame_stride=frame_stride,
            reopen_delay_s=reopen_delay_s,
        )
    return StreamReader(
        source=source,
        frame_stride=frame_stride,
        reopen_delay_s=reopen_delay_s,
    )


def resolve_ml_stream_source(explicit: str | int | None) -> str | int:
    if explicit not in {None, ""}:
        return explicit
    return SHARED_VIDEO_STREAM_SOURCE


class SharedVideoStreamReader:
    """
    Blocking reader that consumes JPEG frames from SharedVideoRuntime.

    Avoids binding the Gazebo UDP port twice when the survey camera proxy is active.
    """

    source = SHARED_VIDEO_STREAM_SOURCE

    def __init__(self, frame_stride: int = 1, reopen_delay_s: float = 0.2):
        self.frame_stride = max(1, int(frame_stride))
        self.reopen_delay_s = max(0.01, float(reopen_delay_s))
        self._frame_id = 0
        self._raw_id = 0
        self._last_seq = 0
        self._opened = False

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def read(self) -> FramePacket | None:
        if not self._opened:
            try:
                self.open()
            except Exception:
                return None

        from backend.infrastructure.camera.runtime import shared_video_runtime

        try:
            seq, jpeg = shared_video_runtime.read_jpeg_frame_sync(
                after_seq=self._last_seq,
                timeout=self.reopen_delay_s + 2.0,
            )
        except Exception:
            return None

        if seq <= self._last_seq or not jpeg:
            return None

        self._last_seq = seq
        self._raw_id += 1
        if self._raw_id % self.frame_stride != 0:
            return None

        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None

        packet = FramePacket(
            frame_id=self._frame_id,
            ts=datetime.utcnow(),
            image=frame,
        )
        self._frame_id += 1
        return packet


class StreamReader:
    """
    Blocking OpenCV reader.

    Important:
    - This class is intentionally synchronous.
    - Call read() via asyncio.to_thread(...) from async code.
    """

    def __init__(self, source: str | int, frame_stride: int = 1, reopen_delay_s: float = 0.2):
        self.source = source
        self.frame_stride = max(1, int(frame_stride))
        self.reopen_delay_s = max(0.01, float(reopen_delay_s))

        self._cap: cv2.VideoCapture | None = None
        self._frame_id = 0
        self._raw_id = 0
        self._opened = False

    def open(self) -> None:
        if self._cap is not None and self._cap.isOpened():
            self._opened = True
            return

        source = self.source
        if isinstance(source, str):
            stripped = source.strip()
            if stripped.isdigit():
                source = int(stripped)

        self._cap = open_video_capture(
            source,
            width=settings.drone_video_width,
            height=settings.drone_video_height,
            fps=settings.drone_video_fps,
            open_timeout_s=settings.drone_video_timeout,
        )
        self._opened = bool(self._cap and self._cap.isOpened())
        if not self._opened:
            raise RuntimeError(f"Cannot open stream: {self.source}")

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self._opened = False

    def read(self) -> FramePacket | None:
        """
        Blocking read.

        Returns:
            FramePacket when a valid frame passes stride filtering.
            None when no frame is currently available.
        """
        if not self._opened or self._cap is None:
            self.open()

        assert self._cap is not None

        ok, frame = self._cap.read()
        if not ok:
            # best-effort reconnect path
            self.close()
            time.sleep(self.reopen_delay_s)
            try:
                self.open()
            except Exception:
                return None
            return None

        self._raw_id += 1
        if self._raw_id % self.frame_stride != 0:
            return None

        packet = FramePacket(
            frame_id=self._frame_id,
            ts=datetime.utcnow(),
            image=frame,
        )
        self._frame_id += 1
        return packet
