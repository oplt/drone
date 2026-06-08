from __future__ import annotations

import os


def _truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def effective_drone_video_use_gazebo() -> bool:
    return _truthy("WAREHOUSE_DRONE_VIDEO_USE_GAZEBO")


def effective_drone_video_source() -> str | None:
    value = os.getenv("WAREHOUSE_DRONE_VIDEO_SOURCE", "").strip()
    return value or None


def warehouse_video_recording_enabled() -> bool:
    return _truthy("WAREHOUSE_VIDEO_RECORDING_ENABLED", "1") and not warehouse_video_blocked()


def warehouse_video_blocked() -> bool:
    return bool(warehouse_video_skip_reason())


def warehouse_video_skip_reason() -> str | None:
    if _truthy("WAREHOUSE_DISABLE_VIDEO"):
        return "Warehouse video is disabled by WAREHOUSE_DISABLE_VIDEO."
    if not effective_drone_video_use_gazebo() and not effective_drone_video_source():
        return "Warehouse video source is not configured."
    return None

