from __future__ import annotations

import logging
import os

from backend.core.config.runtime import settings

logger = logging.getLogger(__name__)


def warehouse_gazebo_sim_enabled() -> bool:
    return os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def effective_drone_video_use_gazebo() -> bool:
    if settings.drone_video_use_gazebo:
        return True
    if warehouse_gazebo_sim_enabled() and (settings.drone_video_source_gazebo or "").strip():
        return True
    return False


def warehouse_video_blocked() -> bool:
    """True when warehouse Gazebo sim should not open Pi/TCP/RTSP streams."""
    if not settings.drone_video_enabled:
        return True
    if not warehouse_gazebo_sim_enabled():
        return False
    return not effective_drone_video_use_gazebo()


def warehouse_video_recording_enabled() -> bool:
    if not settings.drone_video_enabled:
        return False
    if warehouse_gazebo_sim_enabled():
        return effective_drone_video_use_gazebo()
    return True


def resolve_warehouse_video_source() -> str | None:
    if warehouse_gazebo_sim_enabled():
        if settings.drone_video_use_gazebo:
            source = (settings.drone_video_source_gazebo or "").strip()
            return source or None
        return None

    source = (settings.drone_video_source or "").strip()
    if not source:
        return None
    if source.lower().startswith("tcp://") and warehouse_gazebo_sim_enabled():
        return None
    return source


def warehouse_video_skip_reason() -> str | None:
    if not settings.drone_video_enabled:
        return "drone video disabled in configuration"
    if not warehouse_gazebo_sim_enabled():
        return None
    if effective_drone_video_use_gazebo():
        return None
    return (
        "Gazebo warehouse simulation does not use external TCP/RTSP video; "
        "set DRONE_VIDEO_SOURCE_GAZEBO (e.g. udp://127.0.0.1:5600) or disable video."
    )


def effective_drone_video_source() -> str | None:
    if effective_drone_video_use_gazebo():
        source = (settings.drone_video_source_gazebo or "").strip()
        return source or None
    source = (settings.drone_video_source or "").strip()
    return source or None
