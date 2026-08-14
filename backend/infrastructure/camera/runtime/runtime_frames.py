
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import cv2
import numpy as np
from fastapi import Request


class RuntimeFramesMixin:
    """Frame publication, survey frame access, and MJPEG stream."""

    async def _wait_for_first_frame(self, timeout_s: float = 12.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_s
        async with self._condition:
            while self._frame_seq == 0 and not self._last_error:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    break

        if self._frame_seq == 0:
            detail = self._last_error or "Timed out waiting for first video frame."
            raise RuntimeError(detail)

    async def _publish_jpeg_frame(self, encoded_frame: bytes) -> None:
        async with self._condition:
            self._latest_frame = encoded_frame
            self._frame_seq += 1
            self._consecutive_failures = 0
            self._unavailable_until = 0.0
            self._last_error = None
            self._condition.notify_all()
        await self._write_fallback_recording_frame(encoded_frame)

    async def _write_fallback_recording_frame(self, encoded_frame: bytes) -> None:
        async with self._lock:
            writer = self._fallback_video_writer

        if writer is None or not writer.isOpened():
            return

        frame = cv2.imdecode(np.frombuffer(encoded_frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return

        async with self._lock:
            writer = self._fallback_video_writer
            if writer is not None and writer.isOpened():
                writer.write(frame)
    async def wait_for_jpeg_frame(self, after_seq: int, timeout_s: float) -> tuple[int, bytes]:
        deadline = asyncio.get_running_loop().time() + max(0.05, float(timeout_s))
        async with self._condition:
            while self._frame_seq <= after_seq and not self._last_error:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    break

            if self._last_error and self._frame_seq <= after_seq:
                raise RuntimeError(self._last_error)

            frame = self._latest_frame
            if self._frame_seq <= after_seq or not frame:
                raise TimeoutError("Timed out waiting for a new survey camera frame")

            return self._frame_seq, frame

    def read_jpeg_frame_sync(self, after_seq: int, timeout: float) -> tuple[int, bytes]:
        loop = self._loop
        if loop is None or not loop.is_running():
            raise RuntimeError("Survey camera stream is not running yet")

        future = asyncio.run_coroutine_threadsafe(
            self.wait_for_jpeg_frame(after_seq, timeout_s=timeout),
            loop,
        )
        return future.result(timeout=max(0.5, float(timeout)) + 1.0)
    async def stream(self, request: Request) -> AsyncIterator[bytes]:
        last_seq = -1

        while not await request.is_disconnected():
            async with self._condition:
                while self._frame_seq == last_seq and not self._last_error:
                    await self._condition.wait()
                    if await request.is_disconnected():
                        return

                if self._last_error and self._frame_seq == last_seq:
                    error_message = self._last_error
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: text/plain\r\n\r\n"
                        + f"Video stream error: {error_message}\r\n\r\n".encode()
                    )
                    return

                frame = self._latest_frame
                last_seq = self._frame_seq

            if not frame:
                await asyncio.sleep(0.05)
                continue

            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")

