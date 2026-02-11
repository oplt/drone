# backend/api/routes_video.py
import asyncio
import logging
from typing import AsyncIterator, Optional

import httpx
import paramiko
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.config import settings

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


@router.post("/start")
async def start_pi_camera_server():
    """
    Starts the Raspberry Pi streaming server over SSH (best effort).
    Returns the backend proxy URL clients should use.
    """
    stream_src = f"http://{settings.rasperry_ip}:{PI_PORT}/video_feed"

    try:
        # Run SSH in a thread so we don't block the event loop
        await asyncio.to_thread(_start_streaming_server_via_ssh)
    except Exception as e:
        logger.exception("Failed to start Pi camera server via SSH")
        raise HTTPException(status_code=500, detail=f"SSH start failed: {e}")

    # Wait for it to become reachable
    ok = await _wait_for_stream(stream_src, timeout_s=20.0)
    if not ok:
        raise HTTPException(
            status_code=504,
            detail="Pi stream did not become ready in time",
        )

    return {"status": "started", "source": stream_src, "proxy": "/video/mjpeg"}


@router.get("/mjpeg")
async def mjpeg_proxy() -> StreamingResponse:
    """
    Proxies the MJPEG stream from the Raspberry Pi so the frontend can load it
    from the same API origin (avoids CORS/network issues).
    """
    src_url = f"http://{settings.rasperry_ip}:{PI_PORT}/video_feed"

    async def stream_bytes() -> AsyncIterator[bytes]:
        client: Optional[httpx.AsyncClient] = None
        resp: Optional[httpx.Response] = None
        try:
            client = httpx.AsyncClient(timeout=None)
            resp = await client.get(src_url, timeout=None)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Upstream Pi returned {resp.status_code}",
                )

            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk

        finally:
            try:
                if resp is not None:
                    await resp.aclose()
            except Exception:
                pass
            try:
                if client is not None:
                    await client.aclose()
            except Exception:
                pass

    # Preserve MJPEG content type/boundary
    media_type = "multipart/x-mixed-replace; boundary=frame"
    return StreamingResponse(stream_bytes(), media_type=media_type)
