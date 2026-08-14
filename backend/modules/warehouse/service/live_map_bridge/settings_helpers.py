"""Warehouse live-map bridge — typed settings accessors."""

from __future__ import annotations

from backend.core.config.runtime import settings
from backend.modules.warehouse.service.runtime_settings import (
    setting_bool,
    setting_float,
    setting_int,
    setting_text,
)


def _setting_str(name: str, default: str = "") -> str:
    return setting_text(name, default)


def _setting_float(name: str, default: float, *, minimum: float) -> float:
    return setting_float(getattr(settings, name, default), minimum=minimum, default=default)


def _setting_int(name: str, default: int, *, minimum: int) -> int:
    return setting_int(getattr(settings, name, default), minimum=minimum, default=default)


def _setting_bool(name: str, default: bool = False) -> bool:
    return setting_bool(name, default)


__all__ = ["_setting_bool", "_setting_float", "_setting_int", "_setting_str"]
