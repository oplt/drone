from __future__ import annotations

from backend.core.config.runtime import env_truthy, settings


def _setting(name: str, default: object = "") -> object:
    return getattr(settings, name, default)


def _setting_str(name: str, default: str = "") -> str:
    value = _setting(name, default)
    if value is None:
        return default
    return str(value)


def effective_drone_video_use_gazebo() -> bool:
    return env_truthy(_setting("warehouse_drone_video_use_gazebo", False))


def effective_drone_video_source() -> str | None:
    value = _setting_str("warehouse_drone_video_source", "").strip()
    return value or None


def warehouse_video_recording_enabled() -> bool:
    return env_truthy(_setting("warehouse_video_recording_enabled", False)) and not warehouse_video_blocked()


def warehouse_video_blocked() -> bool:
    return warehouse_video_skip_reason() is not None


def warehouse_video_skip_reason() -> str | None:
    if env_truthy(_setting("warehouse_disable_video", False)):
        return "Warehouse video is disabled by WAREHOUSE_DISABLE_VIDEO."
    if not effective_drone_video_use_gazebo() and not effective_drone_video_source():
        return "Warehouse video source is not configured."
    return None
