from __future__ import annotations

import asyncio

import cv2

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime.constants import PI_PORT
from backend.infrastructure.camera.stream_client import DroneVideoStream


class RuntimeCoreMixin:
    """Shared video runtime state initialization."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition()
        self._video: DroneVideoStream | None = None
        self._worker_task: asyncio.Task | None = None
        self._latest_frame: bytes | None = None
        self._frame_seq = 0
        self._last_error: str | None = None
        self._source_url: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._fallback_video_writer: cv2.VideoWriter | None = None
        self._fallback_recording_filename: str | None = None
        self._fallback_recording_path: str | None = None
        self._unavailable_until = 0.0
        self._consecutive_failures = 0
        self._last_failure_log_at = 0.0
        self._gazebo_enable_topics: list[str] = []
        self._gazebo_streaming_enabled = False

    def source_url(self) -> str:
        if settings.drone_video_use_gazebo:
            return settings.drone_video_source_gazebo
        return f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"

