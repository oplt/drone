"""Warehouse mapping stack lifecycle — typed settings accessors."""

from __future__ import annotations

from . import deps


def _setting_float(name: str, default: float) -> float:
    try:
        value = float(getattr(deps.resolve("settings"), name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _setting_int(name: str, default: int) -> int:
    try:
        return max(0, int(getattr(deps.resolve("settings"), name, default)))
    except (TypeError, ValueError):
        return default


__all__ = ["_setting_float", "_setting_int"]
