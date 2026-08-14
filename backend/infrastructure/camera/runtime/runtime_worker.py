
from __future__ import annotations

import asyncio

import cv2

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime.constants import logger
from backend.infrastructure.camera.runtime.gazebo import (
    _get_gazebo_udp_port,
    _gazebo_gst_mjpeg_command,
    gazebo_subprocess_fallback_required,
)
from backend.infrastructure.camera.runtime.shutdown import (
    _is_benign_shutdown_error,
    _is_benign_shutdown_exit_code,
)
from backend.infrastructure.camera.stream_client import DroneVideoStream


class RuntimeWorkerMixin:
    """Background frame capture workers."""

    async def _worker_loop_gazebo_fallback(self) -> None:
        try:
            udp_port = _get_gazebo_udp_port()
        except Exception as exc:
            raise RuntimeError(f"Invalid Gazebo video source configuration: {exc}") from exc

        try:
            proc = await asyncio.create_subprocess_exec(
                *_gazebo_gst_mjpeg_command(udp_port),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("gst-launch-1.0 is not installed") from exc

        buffer = bytearray()
        try:
            if proc.stdout is None:
                raise RuntimeError("Missing stdout pipe for gst-launch fallback")

            while True:
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(64 * 1024), timeout=1.0)
                except TimeoutError:
                    if proc.returncode is not None:
                        if _is_benign_shutdown_exit_code(proc.returncode):
                            logger.info(
                                "gst-launch fallback stopped during shutdown (code %s)",
                                proc.returncode,
                            )
                            return
                        raise RuntimeError(
                            f"gst-launch fallback exited with code {proc.returncode}"
                        )
                    continue

                if not chunk:
                    if proc.returncode is not None:
                        if _is_benign_shutdown_exit_code(proc.returncode):
                            logger.info(
                                "gst-launch fallback stopped during shutdown (code %s)",
                                proc.returncode,
                            )
                            return
                        raise RuntimeError(
                            f"gst-launch fallback exited with code {proc.returncode}"
                        )
                    await asyncio.sleep(0.01)
                    continue

                buffer.extend(chunk)
                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start < 0:
                        if len(buffer) > 2_000_000:
                            del buffer[:-1024]
                        break

                    if start > 0:
                        del buffer[:start]

                    end = buffer.find(b"\xff\xd9", 2)
                    if end < 0:
                        if len(buffer) > 4_000_000:
                            del buffer[:-2_000_000]
                        break

                    frame_bytes = bytes(buffer[: end + 2])
                    del buffer[: end + 2]
                    await self._publish_jpeg_frame(frame_bytes)
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()

    async def _worker_loop(self, source: str) -> None:
        video: DroneVideoStream | None = None
        try:
            if gazebo_subprocess_fallback_required():
                await self._worker_loop_gazebo_fallback()
                return

            video = DroneVideoStream(
                source=source,
                width=settings.drone_video_width,
                height=settings.drone_video_height,
                fps=settings.drone_video_fps,
                open_timeout_s=settings.drone_video_timeout,
                enable_recording=False,
                recording_path=settings.drone_video_save_path,
                recording_format="mp4",
            )

            async with self._lock:
                self._video = video

            frame_iter = video.frames()
            while True:
                packet = await asyncio.to_thread(next, frame_iter, None)
                if packet is None:
                    break
                _width, frame = packet
                ok, encoded = cv2.imencode(".jpg", frame)
                if not ok:
                    continue
                await self._publish_jpeg_frame(encoded.tobytes())
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if _is_benign_shutdown_error(exc):
                logger.info("Shared video runtime stopped during shutdown: %s", exc)
                return
            if (
                self._frame_seq == 0
                and settings.drone_video_use_gazebo
                and "GStreamer support" in str(exc)
            ):
                logger.warning(
                    "OpenCV Gazebo stream failed; falling back to gst-launch source=%s err=%s",
                    source,
                    exc,
                )
                try:
                    await self._worker_loop_gazebo_fallback()
                    return
                except Exception as fallback_exc:
                    exc = fallback_exc

            if self._frame_seq == 0:
                await self._mark_unavailable(str(exc))
            else:
                logger.exception("Shared video runtime failed source=%s", source)
                async with self._condition:
                    self._last_error = str(exc)
                    self._condition.notify_all()
        finally:
            if video is not None:
                video.close()
            async with self._lock:
                if self._video is video:
                    self._video = None
                self._stop_fallback_recording_locked()
                if self._worker_task is asyncio.current_task():
                    self._worker_task = None

