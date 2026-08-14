
from __future__ import annotations

from typing import Any

import httpx

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime.constants import logger
from backend.infrastructure.camera.runtime.gazebo import _ensure_gazebo_streaming_enabled
from backend.infrastructure.camera.runtime.link import drone_video_link_connected
from backend.infrastructure.camera.runtime.source_helpers import (
    _start_streaming_server_via_ssh,
    _wait_for_stream,
)


class RuntimeSourceMixin:
    """HTTP/SSH/Gazebo source bootstrap."""

    async def ensure_source_available(self) -> dict[str, Any]:
        if not drone_video_link_connected():
            return {
                "status": "skipped",
                "source": self.source_url(),
                "proxy": "/video/mjpeg",
                "message": "Drone is not connected.",
            }

        source = self.source_url()
        if settings.drone_video_use_gazebo:
            _ensure_gazebo_streaming_enabled(self)
            return {
                "status": "starting",
                "source": source,
                "proxy": "/video/mjpeg",
                "message": "Gazebo video source selected; waiting for first frame.",
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
            logger.warning("Video source is not reachable after start attempt: %s", source)
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

