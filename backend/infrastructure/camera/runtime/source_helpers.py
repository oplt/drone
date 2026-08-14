from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx
import paramiko

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime.constants import PI_PORT, logger


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
