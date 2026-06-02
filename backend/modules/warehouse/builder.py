import asyncio
import logging
import shutil
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from urllib.parse import urlparse

import cv2
import httpx
import paramiko
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.core.config.runtime import settings
from backend.infrastructure.camera.stream_client import DroneVideoStream, opencv_has_gstreamer
from backend.modules.identity.dependencies import require_user, require_user_header_or_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])

PI_PORT = 5000
_GAZEBO_ENABLE_COOLDOWN_S = 10.0
_last_gazebo_enable_attempt = 0.0


# -------------------- existing helpers (unchanged) --------------------


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
    except Exception as e:
        logger.debug("Unable to list Gazebo topics via 'gz topic -l': %s", e)
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
        except Exception as e:
            logger.warning("Failed to enable Gazebo topic %s: %s", topic, e)


def _get_gazebo_udp_port() -> int:
    source = settings.drone_video_source_gazebo
    parsed = urlparse(source)
    if parsed.scheme.lower() != "udp" or parsed.port is None:
        raise RuntimeError(f"Gazebo source must be udp://host:port (got: {source})")
    return parsed.port


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
                r = await client.get(url)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


async def _gazebo_stream_generator():
    video = None
    try:
        video = DroneVideoStream(
            source=settings.drone_video_source_gazebo,
            width=settings.drone_video_width,
            height=settings.drone_video_height,
            fps=settings.drone_video_fps,
            open_timeout_s=settings.drone_video_timeout,
            enable_recording=False,  # MJPEG view should not force recording
            recording_path=settings.drone_video_save_path,
            recording_format="mp4",
        )

        for _width, frame in video.frames():
            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                continue
            frame_bytes = buffer.tobytes()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            await asyncio.sleep(0.01)

    except Exception as e:
        logger.error(f"Error in Gazebo stream generator: {e}")
        yield (b"--frame\r\nContent-Type: text/plain\r\n\r\nError streaming from Gazebo\r\n\r\n")
    finally:
        if video:
            video.close()


async def _gazebo_stream_generator_auto(request: Request):
    if opencv_has_gstreamer():
        try:
            async for chunk in _gazebo_stream_generator():
                yield chunk
            return
        except Exception as e:
            logger.warning("OpenCV Gazebo stream failed; falling back to gst-launch. err=%s", e)

    async for chunk in _gazebo_gst_fallback_stream_generator(request):
        yield chunk


async def _gazebo_gst_fallback_stream_generator(request: Request):
    try:
        udp_port = _get_gazebo_udp_port()
    except Exception as e:
        logger.error("Gazebo fallback source error: %s", e)
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
            b"--frame\r\nContent-Type: text/plain\r\n\r\ngst-launch-1.0 is not installed\r\n\r\n"
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
            except TimeoutError:
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
            except TimeoutError:
                proc.kill()
                await proc.wait()


# -------------------- NEW: recording manager --------------------

_recorder_lock = asyncio.Lock()
_recorder: DroneVideoStream | None = None
_recorder_task: asyncio.Task | None = None


def _recording_source_url() -> str:
    from backend.modules.warehouse.service.video import (
        effective_drone_video_source,
        effective_drone_video_use_gazebo,
    )

    if effective_drone_video_use_gazebo():
        return effective_drone_video_source() or settings.drone_video_source_gazebo
    return effective_drone_video_source() or f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"


async def _recorder_pump(video: DroneVideoStream):
    """
    Drain frames so OpenCV writer actually receives them.
    Uses asyncio.wait_for so the task responds to cancellation without
    blocking inside the thread indefinitely.
    """
    frame_iter = video.frames()
    while True:
        try:
            packet = await asyncio.wait_for(
                asyncio.to_thread(next, frame_iter, None),
                timeout=2.0,
            )
        except TimeoutError:
            # No frame in 2 s — check for cancellation then retry
            await asyncio.sleep(0)
            continue
        except asyncio.CancelledError:
            break
        if packet is None:
            break
        await asyncio.sleep(0)


@router.post("/recording/start")
async def start_recording(user=Depends(require_user)):
    from backend.modules.warehouse.service.video import (
        warehouse_video_blocked,
        warehouse_video_skip_reason,
    )

    global _recorder, _recorder_task

    if warehouse_video_blocked():
        return {
            "status": "skipped",
            "recording": False,
            "message": warehouse_video_skip_reason(),
        }

    async with _recorder_lock:
        if _recorder and _recorder.get_connection_status().get("recording"):
            return {
                "status": "already_recording",
                "recording_file": _recorder.get_connection_status().get("recording_file"),
            }

        from backend.modules.warehouse.service.video import effective_drone_video_use_gazebo

        if effective_drone_video_use_gazebo():
            await asyncio.to_thread(_ensure_gazebo_streaming_enabled)

        source = _recording_source_url()
        _recorder = DroneVideoStream(
            source=source,
            width=settings.drone_video_width,
            height=settings.drone_video_height,
            fps=settings.drone_video_fps,
            open_timeout_s=settings.drone_video_timeout,
            enable_recording=True,
            recording_path=settings.drone_video_save_path,
            recording_format="mp4",
        )
        _recorder.start_recording()
        _recorder_task = asyncio.create_task(_recorder_pump(_recorder))

        status = _recorder.get_connection_status()
        return {"status": "recording", "recording_file": status.get("recording_file")}


@router.post("/recording/stop")
async def stop_recording(user=Depends(require_user)):
    global _recorder, _recorder_task

    async with _recorder_lock:
        if not _recorder:
            return {"status": "not_recording", "recording_file": None}

        recorder = _recorder
        task = _recorder_task
        _recorder = None
        _recorder_task = None

        filename = recorder.stop_recording()
        recorder.close()

        if task:
            task.cancel()
            with suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(task, timeout=2.0)

        return {"status": "stopped", "recording_file": filename}


@router.get("/recording/status")
async def recording_status(user=Depends(require_user)):
    async with _recorder_lock:
        if not _recorder:
            return {"recording": False, "recording_file": None}
        st = _recorder.get_connection_status()
        return {
            "recording": bool(st.get("recording")),
            "recording_file": st.get("recording_file"),
        }


# -------------------- existing routes (kept) --------------------


@router.post("/start")
async def start_pi_camera_server(user=Depends(require_user)):
    from backend.modules.warehouse.service.video import (
        effective_drone_video_use_gazebo,
        warehouse_video_blocked,
        warehouse_video_skip_reason,
    )

    if warehouse_video_blocked():
        return {
            "status": "skipped",
            "source": None,
            "proxy": "/video/mjpeg",
            "message": warehouse_video_skip_reason(),
        }

    if effective_drone_video_use_gazebo():
        await asyncio.to_thread(_ensure_gazebo_streaming_enabled)
        return {
            "status": "started",
            "source": settings.drone_video_source_gazebo,
            "proxy": "/video/mjpeg",
        }

    stream_src = f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(stream_src)
            if r.status_code == 200:
                return {
                    "status": "already_running",
                    "source": stream_src,
                    "proxy": "/video/mjpeg",
                }
    except Exception:
        pass

    try:
        await asyncio.to_thread(_start_streaming_server_via_ssh)
    except Exception as e:
        logger.warning(f"Failed to start Pi camera server via SSH: {e}")
        return {
            "status": "ssh_failed",
            "message": "Could not start video server via SSH. The stream might still work if it's already running.",
            "source": stream_src,
            "proxy": "/video/mjpeg",
        }

    ok = await _wait_for_stream(stream_src, timeout_s=20.0)
    if not ok:
        return {
            "status": "started_with_warnings",
            "message": "Video server start initiated but not yet reachable",
            "source": stream_src,
            "proxy": "/video/mjpeg",
        }

    return {"status": "started", "source": stream_src, "proxy": "/video/mjpeg"}


@router.get("/mjpeg")
async def mjpeg_proxy(
    request: Request, user=Depends(require_user_header_or_query)
) -> StreamingResponse:
    if settings.drone_video_use_gazebo:
        await asyncio.to_thread(_ensure_gazebo_streaming_enabled)
        media_type = "multipart/x-mixed-replace; boundary=frame"
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        }
        return StreamingResponse(
            _gazebo_stream_generator_auto(request),
            media_type=media_type,
            headers=headers,
        )

    src_url = f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"

    async def stream_bytes() -> AsyncIterator[bytes]:
        retry_count = 0
        max_retries = 3

        while retry_count < max_retries and not await request.is_disconnected():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("GET", src_url, timeout=None) as resp:
                        if resp.status_code != 200:
                            error_frame = (
                                "--frame\r\n"
                                "Content-Type: text/plain\r\n\r\n"
                                f"Video stream unavailable (HTTP {resp.status_code})\r\n"
                                "\r\n"
                            ).encode()
                            yield error_frame
                            await asyncio.sleep(5)
                            retry_count += 1
                            continue

                        retry_count = 0
                        async for chunk in resp.aiter_bytes():
                            if await request.is_disconnected():
                                return
                            if chunk:
                                yield chunk

            except Exception as e:
                logger.warning("Video stream error: %s", e)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: text/plain\r\n\r\n"
                    b"Video stream error. Reconnecting...\r\n"
                    b"\r\n"
                )
                retry_count += 1
                await asyncio.sleep(2)

        if retry_count >= max_retries:
            yield (
                b"--frame\r\n"
                b"Content-Type: text/plain\r\n\r\n"
                b"Video stream unavailable - please check connection\r\n"
                b"\r\n"
            )

    media_type = "multipart/x-mixed-replace; boundary=frame"
    return StreamingResponse(stream_bytes(), media_type=media_type)
