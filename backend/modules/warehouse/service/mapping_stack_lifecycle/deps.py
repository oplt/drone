"""Warehouse mapping stack lifecycle — test monkeypatching helpers."""

from __future__ import annotations

from backend.core.config.runtime import settings as _default_settings

settings = _default_settings


def resolve(name: str):
    from backend.modules.warehouse.service import mapping_stack_lifecycle as pkg

    return getattr(pkg, name)


def set_state(name: str, value) -> None:
    from backend.modules.warehouse.service import mapping_stack_lifecycle as pkg

    setattr(pkg, name, value)


__all__ = ["resolve", "set_state", "settings"]
