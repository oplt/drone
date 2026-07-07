from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.config.runtime import env_truthy, settings


def setting_text(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def setting_float(value: Any, *, minimum: float, default: float) -> float:
    try:
        return max(minimum, float(value))
    except (TypeError, ValueError):
        return max(minimum, default)


def setting_int(value: Any, *, minimum: int = 0, default: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return max(minimum, default)


def setting_bool(name: str, default: bool = False) -> bool:
    raw = getattr(settings, name, default)
    if isinstance(raw, str):
        return env_truthy(raw)
    return bool(raw)


def ros2_workspace() -> Path:
    raw = setting_text("warehouse_ros2_ws", "ros2_ws") or "ros2_ws"
    return Path(raw).expanduser().resolve()
