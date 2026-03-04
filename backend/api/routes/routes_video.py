import asyncio
import logging
import shutil
import subprocess
import time
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx
import paramiko
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import cv2

from backend.config import settings
from backend.auth.deps import require_user, require_user_header_or_query
from backend.video.stream import DroneVideoStream, opencv_has_gstreamer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])

PI_PORT = 5000
_GAZEBO_ENABLE_COOLDOWN_S = 10.0
_last_gazebo_enable_attempt = 0.0


def _discover_gazebo_enable_topics() -> list[str]:
    """
    Discover Gazebo camera enable topics so the stream can be turned on automatically.
    """
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
        if topic.endswith("/enable_streaming") and (
            "camera" in topic or "sensor" in topic
        ):
            topics.append(topic)

    return topics


def _ensure_gazebo_streaming_enabled() -> None:
    """
    Best effort: publish 'data: 1' to discovered Gazebo camera enable topics.
    """
    global _last_gazebo_enable_attempt

    now = time.monotonic()
    if now - _last_gazebo_enable_attempt < _GAZEBO_ENABLE_COOLDOWN_S:
        return
    _last_gazebo_enable_attempt = now

    topics = _discover_gazebo_enable_topics()
    if not topics:
        logger.warning(
            "No Gazebo /enable_streaming topic discovered. Camera stream may stay disabled."
        )
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
        raise RuntimeError(
            f"Gazebo source must be udp://host:port for fallback mode (got: {source})"
        )
    return parsed.port


def _start_streaming_server_via_ssh() -> None:
    """
    Start the Raspberry Pi Flask camera server in background via SSH.
    Uses the same approach as pc_view_stream.py.
    """
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

    ssh.connect(
        hostname=pi_host,
        username=pi_user,
        key_filename=ssh_key,
        timeout=10,
    )
    ssh.exec_command(command)
    ssh.close()


async def _wait_for_stream(url: str, timeout_s: float = 15.0) -> bool:
    """
    Poll the MJPEG endpoint until it's reachable (HTTP 200) or timeout.
    """
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
    """
    Generator for Gazebo video stream.
    Creates a temporary DroneVideoStream to capture frames from Gazebo.
    """
    video = None
    try:
        # Create a temporary video stream instance for this request
        # Note: In a production environment, you might want to share a single instance
        # or use the one from the orchestrator if available.
        video = DroneVideoStream(
            source=settings.drone_video_source_gazebo,
            width=settings.drone_video_width,
            height=settings.drone_video_height,
            fps=settings.drone_video_fps,
            open_timeout_s=settings.drone_video_timeout,
        )

        logger.info(f"Started Gazebo stream from {settings.drone_video_source_gazebo}")

        for width, frame in video.frames():
            # Encode frame as JPEG
            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )

            # Small sleep to yield control
            await asyncio.sleep(0.01)

    except Exception as e:
        logger.error(f"Error in Gazebo stream generator: {e}")
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"Error streaming from Gazebo\r\n\r\n"
        )
    finally:
        if video:
            video.close()


async def _gazebo_stream_generator_auto(request: Request):
    """
    Try OpenCV first (fast path). If it fails (common with RTP cap mismatches),
    fall back to gst-launch multipart stream.
    """
    if opencv_has_gstreamer():
        try:
            async for chunk in _gazebo_stream_generator():
                # _gazebo_stream_generator yields bytes
                yield chunk
            return
        except Exception as e:
            logger.warning("OpenCV Gazebo stream failed; falling back to gst-launch. err=%s", e)

    # Fallback (more robust for RTP)
    async for chunk in _gazebo_gst_fallback_stream_generator(request):
        yield chunk


async def _gazebo_gst_fallback_stream_generator(request: Request):
    """
    Fallback path when OpenCV is built without GStreamer support.
    Streams multipart MJPEG directly from gst-launch output.
    """
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
        # Keep this as ONE argv item; no shell quoting needed
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
        logger.error("gst-launch-1.0 not found; cannot run Gazebo fallback stream")
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"gst-launch-1.0 is not installed\r\n\r\n"
        )
        return
    except Exception as e:
        logger.error("Failed to start Gazebo fallback stream process: %s", e)
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"Failed to start Gazebo fallback stream\r\n\r\n"
        )
        return

    logger.warning(
        "OpenCV has no GStreamer support. Using gst-launch fallback for Gazebo stream."
    )

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
                    raise RuntimeError(
                        f"gst-launch fallback exited with code {proc.returncode}"
                    )
                continue

            if chunk:
                yield chunk
                continue

            if proc.returncode is not None:
                raise RuntimeError(
                    f"gst-launch fallback exited with code {proc.returncode}"
                )

            await asyncio.sleep(0.01)

    except Exception as e:
        logger.error("Error in Gazebo gst-launch fallback generator: %s", e)
        yield (
            b"--frame\r\n"
            b"Content-Type: text/plain\r\n\r\n"
            b"Error streaming from Gazebo fallback\r\n\r\n"
        )
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

@router.post("/start")
async def start_pi_camera_server(user=Depends(require_user)):
    """
    Starts the Raspberry Pi streaming server over SSH (best effort).
    Returns the backend proxy URL clients should use.
    """
    if settings.drone_video_use_gazebo:
        await asyncio.to_thread(_ensure_gazebo_streaming_enabled)
        return {
            "status": "started",
            "source": settings.drone_video_source_gazebo,
            "proxy": "/video/mjpeg",
        }

    stream_src = f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"

    # First, check if the stream is already accessible
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(stream_src)
            if r.status_code == 200:
                logger.info("Video stream already running")
                return {"status": "already_running", "source": stream_src, "proxy": "/video/mjpeg"}
    except Exception:
        pass  # Stream not accessible, try to start it

    # Try to start via SSH
    try:
        await asyncio.to_thread(_start_streaming_server_via_ssh)
    except Exception as e:
        logger.warning(f"Failed to start Pi camera server via SSH: {e}")
        # Don't fail the request - just return a warning
        return {
            "status": "ssh_failed",
            "message": "Could not start video server via SSH. The stream might still work if it's already running.",
            "source": stream_src,
            "proxy": "/video/mjpeg"
        }

    # Wait for it to become reachable
    ok = await _wait_for_stream(stream_src, timeout_s=20.0)
    if not ok:
        logger.warning("Pi stream did not become ready in time, but will still attempt to proxy")
        # Return success anyway - the proxy will handle connection errors
        return {
            "status": "started_with_warnings",
            "message": "Video server start initiated but not yet reachable",
            "source": stream_src,
            "proxy": "/video/mjpeg"
        }

    return {"status": "started", "source": stream_src, "proxy": "/video/mjpeg"}

@router.get("/mjpeg")
async def mjpeg_proxy(request: Request, user=Depends(require_user_header_or_query)) -> StreamingResponse:
    """
    Proxies the MJPEG stream from the Raspberry Pi so the frontend can load it
    from the same API origin (avoids CORS/network issues).
    """
    
    # If using Gazebo, stream directly from Gazebo source
    if settings.drone_video_use_gazebo:
        await asyncio.to_thread(_ensure_gazebo_streaming_enabled)
        media_type = "multipart/x-mixed-replace; boundary=frame"
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        }
        return StreamingResponse(_gazebo_stream_generator_auto(request), media_type=media_type,headers=headers)

    src_url = f"http://{settings.raspberry_ip}:{PI_PORT}/video_feed"

    async def stream_bytes() -> AsyncIterator[bytes]:
        """Generator function that yields video frames"""
        retry_count = 0
        max_retries = 3

        while retry_count < max_retries and not await request.is_disconnected():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    try:
                        async with client.stream("GET", src_url, timeout=None) as resp:
                            if resp.status_code != 200:
                                # Yield an error frame instead of raising exception
                                error_frame = (
                                    "--frame\r\n"
                                    "Content-Type: text/plain\r\n\r\n"
                                    f"Video stream unavailable (HTTP {resp.status_code})\r\n"
                                    "\r\n"
                                ).encode()
                                yield error_frame
                                await asyncio.sleep(5)  # Wait before retry
                                retry_count += 1
                                continue

                            # Reset retry count on successful connection
                            retry_count = 0

                            async for chunk in resp.aiter_bytes():
                                if await request.is_disconnected():
                                    return
                                if chunk:
                                    yield chunk

                    except httpx.ConnectError as e:
                        logger.warning(f"Connection error to video source {src_url}: {e}")
                        # Yield a warning frame
                        error_frame = (
                            b"--frame\r\n"
                            b"Content-Type: text/plain\r\n\r\n"
                            b"Cannot connect to video source. Retrying...\r\n"
                            b"\r\n"
                        )
                        yield error_frame
                        retry_count += 1
                        await asyncio.sleep(2)

                    except httpx.TimeoutException as e:
                        logger.warning(f"Timeout connecting to video source {src_url}: {e}")
                        error_frame = (
                            b"--frame\r\n"
                            b"Content-Type: text/plain\r\n\r\n"
                            b"Video source timeout. Retrying...\r\n"
                            b"\r\n"
                        )
                        yield error_frame
                        retry_count += 1
                        await asyncio.sleep(2)

                    except httpx.HTTPError as e:
                        logger.warning(f"HTTP error from video source {src_url}: {e}")
                        error_frame = (
                            b"--frame\r\n"
                            b"Content-Type: text/plain\r\n\r\n"
                            b"Video source error. Retrying...\r\n"
                            b"\r\n"
                        )
                        yield error_frame
                        retry_count += 1
                        await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Unexpected error in video stream: {e}")
                error_frame = (
                    b"--frame\r\n"
                    b"Content-Type: text/plain\r\n\r\n"
                    b"Video stream error. Reconnecting...\r\n"
                    b"\r\n"
                )
                yield error_frame
                retry_count += 1
                await asyncio.sleep(2)

        # If we've exhausted retries
        if retry_count >= max_retries:
            final_frame = (
                b"--frame\r\n"
                b"Content-Type: text/plain\r\n\r\n"
                b"Video stream unavailable - please check connection\r\n"
                b"\r\n"
            )
            yield final_frame

    # Preserve MJPEG content type/boundary
    media_type = "multipart/x-mixed-replace; boundary=frame"
    return StreamingResponse(stream_bytes(), media_type=media_type)
