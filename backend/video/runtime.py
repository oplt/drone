from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlparse

import cv2
import httpx
import paramiko
from fastapi import Request

from backend.config import settings
from backend.video.stream import DroneVideoStream, opencv_has_gstreamer


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
        if topic.endswith("/enable_streaming") and (
            "camera" in topic or "sensor" in topic
        ):
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


async def gazebo_gst_fallback_stream(request: Request) -> AsyncIterator[bytes]:
    try:
        udp_port = _get_gazebo_udp_port()
    except Exception as exc:
        logger.error("Gazebo fallback source error: %s", exc)
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"Invalid Gazebo video source configuration\r\n\r\n"
        )
        return

    cmd = [
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

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"gst-launch-1.0 is not installed\r\n\r\n"
        )
        return

    try:
        if proc.stdout is None:
            raise RuntimeError("Missing stdout pipe for gst-launch fallback")
        while True:
            if await request.is_disconnected():
                break

            try:
                chunk = await asyncio.wait_for(proc.stdout.read(64 * 1024), timeout=1.0)
            except asyncio.TimeoutError:
                if proc.returncode is not None:
                    raise RuntimeError(f"gst-launch fallback exited with code {proc.returncode}")
                continue

            if chunk:
                yield chunk
                continue

            if proc.returncode is not None:
                raise RuntimeError(f"gst-launch fallback exited with code {proc.returncode}")

            await asyncio.sleep(0.01)

    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()


def _start_streaming_server_via_ssh() -> None:
    pi_host = settings.raspberry_ip
    pi_user = settings.raspberry_user
    ssh_key = settings.ssh_key_path
    remote_script = settings.raspberry_streaming_script_path

    if not all([pi_host, pi_user, ssh_key, remote_script]):
        raise RuntimeError("Missing Raspberry Pi SSH settings in backend.config.settings")

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


class SharedVideoRuntime:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition()
        self._video: Optional[DroneVideoStream] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._latest_frame: Optional[bytes] = None
        self._frame_seq = 0
        self._last_error: Optional[str] = None
        self._source_url: Optional[str] = None

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
                except asyncio.TimeoutError:
                    break

        if self._frame_seq == 0:
            detail = self._last_error or "Timed out waiting for first video frame."
            raise RuntimeError(detail)

    async def ensure_running(self) -> dict[str, Any]:
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
        video: Optional[DroneVideoStream] = None
        try:
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
                async with self._condition:
                    self._latest_frame = encoded.tobytes()
                    self._frame_seq += 1
                    self._condition.notify_all()
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
                if self._worker_task is asyncio.current_task():
                    self._worker_task = None

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            task = self._worker_task
            video = self._video
            source = self._source_url or self.source_url()

        started = task is not None and not task.done()
        state = video.get_connection_status() if video is not None else {}
        recording_path = video.recording_full_path() if video is not None else None
        return {
            "started": started,
            "healthy": bool(state.get("healthy")) if state else False,
            "frame_count": int(state.get("frame_count") or 0),
            "recording": bool(state.get("recording")) if state else False,
            "recording_file": state.get("recording_file") if state else None,
            "recording_path": recording_path,
            "source": source,
            "error": self._last_error,
        }

    async def start_recording(self, *, recording_path: str | None = None) -> dict[str, Any]:
        if gazebo_subprocess_fallback_required():
            return {
                "recording": False,
                "recording_file": None,
                "recording_path": None,
                "error": (
                    "Backend video recording is unavailable for Gazebo UDP streams "
                    "because this OpenCV build has no GStreamer support."
                ),
            }

        await self.ensure_running()
        recording_root = _recording_root_from_path(recording_path)

        async with self._lock:
            if self._video is None:
                raise RuntimeError("Shared video stream is not available.")
            self._video.recording_path = str(recording_root)
            filename = self._video.start_recording()
            full_path = self._video.recording_full_path()

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
            if self._video is None:
                return {
                    "recording": False,
                    "recording_file": None,
                    "recording_path": None,
                }
            full_path = self._video.recording_full_path()
            filename = self._video.stop_recording()

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
                        + f"Video stream error: {error_message}\r\n\r\n".encode("utf-8")
                    )
                    return

                frame = self._latest_frame
                last_seq = self._frame_seq

            if not frame:
                await asyncio.sleep(0.05)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )


shared_video_runtime = SharedVideoRuntime()
