from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime.constants import (
    _DRONE_DISCONNECTED_RETRY_MS,
    _UNAVAILABLE_BACKOFF_BASE_S,
    _UNAVAILABLE_BACKOFF_MAX_S,
    logger,
)
from backend.infrastructure.camera.runtime.link import drone_video_link_connected


class RuntimeLifecycleMixin:
    """Worker lifecycle, backoff, and readiness reporting."""

    async def _mark_unavailable(self, detail: str) -> None:
        now = time.monotonic()
        self._consecutive_failures += 1
        backoff_s = min(
            _UNAVAILABLE_BACKOFF_MAX_S,
            _UNAVAILABLE_BACKOFF_BASE_S * (2 ** (self._consecutive_failures - 1)),
        )
        self._unavailable_until = now + backoff_s
        self._last_error = detail
        if now - self._last_failure_log_at >= backoff_s:
            logger.warning(
                "Video stream unavailable source=%s error=%s retry_after_ms=%d failures=%d",
                self._source_url or self.source_url(),
                detail,
                int(backoff_s * 1000),
                self._consecutive_failures,
            )
            self._last_failure_log_at = now

        async with self._lock:
            task = self._worker_task
            video = self._video
            self._worker_task = None
            self._video = None
            self._latest_frame = None
            self._frame_seq = 0

        if task is not None and not task.done():
            if task is asyncio.current_task():
                async with self._lock:
                    self._worker_task = None
            else:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if video is not None:
            video.close()

        async with self._condition:
            self._condition.notify_all()

    def _retry_after_ms(self) -> int:
        remaining = self._unavailable_until - time.monotonic()
        return max(0, int(remaining * 1000))

    async def ensure_running(self) -> dict[str, Any]:
        self._loop = asyncio.get_running_loop()
        if not drone_video_link_connected():
            raise RuntimeError("Drone is not connected")

        retry_after_ms = self._retry_after_ms()
        if retry_after_ms > 0:
            detail = self._last_error or "Video stream is in backoff after a recent failure."
            raise RuntimeError(f"{detail} (retry after {retry_after_ms}ms)")

        already_running = False
        async with self._lock:
            task = self._worker_task
            if task is not None and not task.done():
                already_running = True

        if already_running:
            status = await self.readiness_status()
            if (
                not status.get("first_frame_available")
                and status.get("error")
            ):
                raise RuntimeError(str(status["error"]))
            return status

        availability = await self.ensure_source_available()
        source = str(availability.get("source") or self.source_url())

        async with self._lock:
            task = self._worker_task
            if task is None or task.done():
                self._latest_frame = None
                self._frame_seq = 0
                self._last_error = None
                self._source_url = source
                self._worker_task = asyncio.create_task(self._worker_loop(source))

        try:
            await self._wait_for_first_frame()
        except RuntimeError as exc:
            await self._mark_unavailable(str(exc))
            raise

        return await self.readiness_status()

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            task = self._worker_task
            video = self._video
            source = self._source_url or self.source_url()
            fallback_recording = bool(
                self._fallback_video_writer is not None and self._fallback_video_writer.isOpened()
            )
            fallback_recording_file = self._fallback_recording_filename
            fallback_recording_path = self._fallback_recording_path
            frame_seq = self._frame_seq

        started = task is not None and not task.done()
        state = video.get_connection_status() if video is not None else {}
        recording_path = video.recording_full_path() if video is not None else None
        return {
            "started": started,
            "healthy": (
                bool(state.get("healthy"))
                if state
                else bool(started and frame_seq > 0 and not self._last_error)
            ),
            "frame_count": int(state.get("frame_count") or frame_seq),
            "recording": bool(state.get("recording")) if state else fallback_recording,
            "recording_file": (state.get("recording_file") if state else fallback_recording_file),
            "recording_path": recording_path or fallback_recording_path,
            "source": source,
            "error": self._last_error,
        }

    async def readiness_status(self) -> dict[str, Any]:
        base = await self.status()
        retry_after_ms = self._retry_after_ms()
        first_frame_available = int(base.get("frame_count") or 0) > 0
        drone_connected = drone_video_link_connected()
        if not drone_connected and not first_frame_available:
            stream_state = "waiting_for_drone"
            retry_after_ms = max(retry_after_ms, _DRONE_DISCONNECTED_RETRY_MS)
        elif first_frame_available and base.get("healthy"):
            stream_state = "ready"
        elif retry_after_ms > 0:
            stream_state = "unavailable"
        elif base.get("started"):
            stream_state = "warming"
        else:
            stream_state = "idle"

        return {
            **base,
            "state": stream_state,
            "first_frame_available": first_frame_available,
            "drone_connected": drone_connected,
            "camera_stream_topic_found": bool(self._gazebo_enable_topics),
            "gazebo_streaming_enabled": self._gazebo_streaming_enabled,
            "udp_first_frame_received": bool(
                first_frame_available and settings.drone_video_use_gazebo
            ),
            "last_error": self._last_error,
            "retry_after_ms": retry_after_ms,
            "failure_count": self._consecutive_failures,
        }

    async def stop(self) -> None:
        async with self._lock:
            task = self._worker_task
            video = self._video
            self._worker_task = None
            self._video = None
            self._last_error = "Video runtime stopped."
            self._stop_fallback_recording_locked()

        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if video is not None:
            video.close()
