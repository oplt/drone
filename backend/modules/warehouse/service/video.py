from __future__ import annotations

from backend.core.config.runtime import env_truthy, settings


def effective_drone_video_use_gazebo() -> bool:
    return env_truthy(settings.warehouse_drone_video_use_gazebo)


def effective_drone_video_source() -> str | None:
    value = settings.warehouse_drone_video_source.strip()
    return value or None


def warehouse_video_recording_enabled() -> bool:
    return env_truthy(settings.warehouse_video_recording_enabled) and not warehouse_video_blocked()


def warehouse_video_blocked() -> bool:
    return bool(warehouse_video_skip_reason())


def warehouse_video_skip_reason() -> str | None:
    if env_truthy(settings.warehouse_disable_video):
        return "Warehouse video is disabled by WAREHOUSE_DISABLE_VIDEO."
    if not effective_drone_video_use_gazebo() and not effective_drone_video_source():
        return "Warehouse video source is not configured."
    return None

