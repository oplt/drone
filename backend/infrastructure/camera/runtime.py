from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import cv2
import httpx
import numpy as np
import paramiko
from fastapi import Request

from backend.core.config.runtime import settings
from backend.infrastructure.camera.stream_client import DroneVideoStream, opencv_has_gstreamer

logger = logging.getLogger(__name__)

PI_PORT = 5000
_GAZEBO_ENABLE_COOLDOWN_S = 10.0
_last_gazebo_enable_attempt = 0.0


def gazebo_subprocess_fallback_required() -> bool:
    return bool(settings.drone_video_use_gazebo and not opencv_has_gstreamer())


def _get_gazebo_udp_port() -> int:
    source = settings.drone_video_source_gazebo
    parsed = urlparse(source)
    if parsed.scheme.lower() != "udp" or parsed.port is None:
        raise RuntimeError(f"Gazebo source must be udp://host:port (got: {source})")
    return parsed.port


def _discover_gazebo_enable_topics() -> list[str]:
    if shutil.which("gz") is None:
        return []
    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=True,
        )
    except Exception as exc:
        logger.debug("Unable to list Gazebo topics via 'gz topic -l': %s", exc)
        return []

    topics: list[str] = []
    for line in result.stdout.splitlines():
        topic = line.strip()
        if not topic:
            continue
        if topic.endswith("/enable_streaming") and ("camera" in topic or "sensor" in topic):
            topics.append(topic)
    return topics


def _ensure_gazebo_streaming_enabled() -> None:
    global _last_gazebo_enable_attempt

    now = time.monotonic()
    if now - _last_gazebo_enable_attempt < _GAZEBO_ENABLE_COOLDOWN_S:
        return
    _last_gazebo_enable_attempt = now

    topics = _discover_gazebo_enable_topics()
    if not topics:
        logger.warning("No Gazebo /enable_streaming topic discovered.")
        return

    for topic in topics:
        try:
            subprocess.run(
                ["gz", "topic", "-t", topic, "-m", "gz.msgs.Boolean", "-p", "data: 1"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=True,
            )
            logger.info("Enabled Gazebo camera stream topic: %s", topic)
        except Exception as exc:
            logger.warning("Failed to enable Gazebo topic %s: %s", topic, exc)


def _gazebo_gst_mjpeg_command(udp_port: int) -> list[str]:
    return [
        "gst-launch-1.0",
        "-q",
        "udpsrc",
        f"port={udp_port}",
        "caps=application/x-rtp,media=(string)video,clock-rate=(int)90000,encoding-name=(string)H264,payload=(int)96",
        "!",
        "rtpjitterbuffer",
        "!",
        "rtph264depay",
        "!",
        "h264parse",
        "config-interval=-1",
        "!",
        "avdec_h264",
        "!",
        "videoconvert",
        "!",
        "jpegenc",
        "!",
        "multipartmux",
        "boundary=frame",
        "!",
        "fdsink",
        "fd=1",
    ]


def _start_streaming_server_via_ssh() -> None:
    pi_host = settings.raspberry_ip
    pi_user = settings.raspberry_user
    ssh_key = settings.ssh_key_path
    remote_script = settings.raspberry_streaming_script_path

    if not all([pi_host, pi_user, ssh_key, remote_script]):
        raise RuntimeError(
            "Missing Raspberry Pi SSH settings in backend.core.config.runtime.settings"
        )

    command = f"nohup python3 {remote_script} > /tmp/pi_cam_server.log 2>&1 &"

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=pi_host, username=pi_user, key_filename=ssh_key, timeout=10)
    ssh.exec_command(command)
    ssh.close()


async def _wait_for_stream(url: str, timeout_s: float = 15.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_s
    async with httpx.AsyncClient(timeout=3.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


def _recording_root_from_path(recording_path: str | None) -> Path:
    raw = (recording_path or "").strip() or settings.drone_video_save_path
    path = Path(raw).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _recording_filename(recording_format: str = "mp4") -> str:
    return f"drone_video_{time.strftime('%Y%m%d_%H%M%S')}.{recording_format}"


class SharedVideoRuntime:
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

    def source_url(self) -> str:
        if settings.drone_video_use_gazebo:
            return settings.drone_video_source_gazebo
        return f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"

    async def ensure_source_available(self) -> dict[str, Any]:
        source = self.source_url()
        if settings.drone_video_use_gazebo:
            await asyncio.to_thread(_ensure_gazebo_streaming_enabled)
            return {
                "status": "ready",
                "source": source,
                "proxy": "/video/mjpeg",
            }

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(source)
                if response.status_code == 200:
                    return {
                        "status": "already_running",
                        "source": source,
                        "proxy": "/video/mjpeg",
                    }
        except Exception:
            pass

        try:
            await asyncio.to_thread(_start_streaming_server_via_ssh)
        except Exception as exc:
            logger.warning("Failed to start Pi camera server via SSH: %s", exc)
            return {
                "status": "ssh_failed",
                "source": source,
                "proxy": "/video/mjpeg",
                "message": (
                    "Could not start video server via SSH. "
                    "The stream might still work if it is already running."
                ),
            }

        reachable = await _wait_for_stream(source, timeout_s=20.0)
        if not reachable:
            return {
                "status": "started_with_warnings",
                "source": source,
                "proxy": "/video/mjpeg",
                "message": "Video server start initiated but not yet reachable.",
            }

        return {
            "status": "started",
            "source": source,
            "proxy": "/video/mjpeg",
        }

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

    def _start_fallback_recording_locked(self, *, recording_root: Path) -> tuple[str, str]:
        writer = self._fallback_video_writer
        if writer is not None and writer.isOpened():
            return (
                self._fallback_recording_filename or "",
                self._fallback_recording_path or "",
            )

        latest_frame = self._latest_frame
        if latest_frame is None:
            raise RuntimeError("No video frame is available for Gazebo recording yet.")

        frame = cv2.imdecode(np.frombuffer(latest_frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("Failed to decode current Gazebo video frame.")

        filename = _recording_filename("mp4")
        full_path = recording_root / filename
        fps = max(1.0, float(settings.drone_video_fps or 30))
        writer = cv2.VideoWriter(
            str(full_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (int(frame.shape[1]), int(frame.shape[0])),
        )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError(f"Failed to open video writer for {full_path}")

        writer.write(frame)
        self._fallback_video_writer = writer
        self._fallback_recording_filename = filename
        self._fallback_recording_path = str(full_path)
        logger.info("Started Gazebo fallback recording: %s", full_path)
        return filename, str(full_path)

    def _stop_fallback_recording_locked(self) -> tuple[str | None, str | None]:
        filename = self._fallback_recording_filename
        full_path = self._fallback_recording_path
        writer = self._fallback_video_writer
        self._fallback_video_writer = None
        if writer is not None:
            writer.release()
            if full_path:
                logger.info("Stopped Gazebo fallback recording: %s", full_path)
        return filename, full_path

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
                        raise RuntimeError(
                            f"gst-launch fallback exited with code {proc.returncode}"
                        )
                    continue

                if not chunk:
                    if proc.returncode is not None:
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

    async def ensure_running(self) -> dict[str, Any]:
        self._loop = asyncio.get_running_loop()
        already_running = False
        async with self._lock:
            task = self._worker_task
            if task is not None and not task.done():
                already_running = True

        if already_running:
            return await self.status()

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

        await self._wait_for_first_frame()
        return await self.status()

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
            logger.exception("Shared video runtime failed")
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

    async def start_recording(self, *, recording_path: str | None = None) -> dict[str, Any]:
        await self.ensure_running()
        recording_root = _recording_root_from_path(recording_path)

        async with self._lock:
            if self._video is not None:
                self._video.recording_path = str(recording_root)
                filename = self._video.start_recording()
                full_path = self._video.recording_full_path()
            else:
                filename, full_path = self._start_fallback_recording_locked(
                    recording_root=recording_root
                )

        status = await self.status()
        status.update(
            {
                "recording": bool(filename),
                "recording_file": filename,
                "recording_path": full_path,
            }
        )
        return status

    async def stop_recording(self) -> dict[str, Any]:
        async with self._lock:
            if self._video is not None:
                full_path = self._video.recording_full_path()
                filename = self._video.stop_recording()
            else:
                filename, full_path = self._stop_fallback_recording_locked()
                if filename is None and full_path is None:
                    return {
                        "recording": False,
                        "recording_file": None,
                        "recording_path": None,
                    }

        status = await self.status()
        status.update(
            {
                "recording": False,
                "recording_file": filename,
                "recording_path": full_path,
            }
        )
        return status

    async def stream(self, request: Request) -> AsyncIterator[bytes]:
        await self.ensure_running()
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


shared_video_runtime = SharedVideoRuntime()
