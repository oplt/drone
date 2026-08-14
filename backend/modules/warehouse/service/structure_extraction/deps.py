"""Mutable dependency refs for test monkeypatching."""

from __future__ import annotations

from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage as _default_warehouse_live_map_chunk_storage,
)

warehouse_live_map_chunk_storage = _default_warehouse_live_map_chunk_storage


def resolve_chunk_storage():
    from backend.modules.warehouse.service import structure_extraction as sx

    return sx.warehouse_live_map_chunk_storage


def resolve(name: str):
    from backend.modules.warehouse.service import structure_extraction as sx

    return getattr(sx, name)


__all__ = ["resolve", "resolve_chunk_storage", "warehouse_live_map_chunk_storage"]
