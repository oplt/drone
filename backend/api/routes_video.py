import asyncio
import logging
from typing import AsyncIterator

import httpx
import paramiko
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.auth.deps import require_admin, require_user_header_or_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])

PI_PORT = 5000


def _start_streaming_server_via_ssh() -> None:
    """
    Start the Raspberry Pi Flask camera server in background via SSH.
    Uses the same approach as pc_view_stream.py.
    """
    pi_host = settings.rasperry_ip
    pi_user = settings.rasperry_user
    ssh_key = settings.ssh_key_path
    remote_script = settings.rasperry_streaming_script_path

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


# In routes_video.py, add better error handling and fallback

@router.post("/start")
async def start_pi_camera_server(user=Depends(require_admin)):
    """
    Starts the Raspberry Pi streaming server over SSH (best effort).
    Returns the backend proxy URL clients should use.
    """
    stream_src = f"http://{settings.rasperry_ip}:{PI_PORT}/video_feed"

    # First, check if the stream is already accessible
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(stream_src)
            if r.status_code == 200:
                logger.info("Video stream already running")
                return {"status": "already_running", "source": stream_src, "proxy": "/video/mjpeg"}
    except:
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
    src_url = f"http://{settings.rasperry_ip}:{PI_PORT}/video_feed"

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