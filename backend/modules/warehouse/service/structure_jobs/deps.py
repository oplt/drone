"""Mutable dependency refs for structure job modules (test monkeypatching)."""

from __future__ import annotations

from typing import Any, Callable

from backend.modules.warehouse.service.live_map_manifest import (
    load_flight_manifest as _default_load_flight_manifest,
)
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage as _default_warehouse_live_map_chunk_storage,
)

load_flight_manifest = _default_load_flight_manifest
warehouse_live_map_chunk_storage = _default_warehouse_live_map_chunk_storage


def resolve_chunk_storage():
    """Read chunk storage from the public package (supports test monkeypatching)."""
    from backend.modules.warehouse.service import structure_jobs as sj

    return sj.warehouse_live_map_chunk_storage


def resolve_load_flight_manifest() -> Callable[[str], Any]:
    """Read manifest loader from the public package (supports test monkeypatching)."""
    from backend.modules.warehouse.service import structure_jobs as sj

    return sj.load_flight_manifest


def resolve_worker_ready_cache() -> tuple[float, bool, str | None] | None:
    from backend.modules.warehouse.service import structure_jobs as sj

    return sj._WORKER_READY_CACHE


def set_worker_ready_cache(value: tuple[float, bool, str | None] | None) -> None:
    from backend.modules.warehouse.service import structure_jobs as sj

    sj._WORKER_READY_CACHE = value


__all__ = [
    "load_flight_manifest",
    "resolve_chunk_storage",
    "resolve_load_flight_manifest",
    "resolve_worker_ready_cache",
    "set_worker_ready_cache",
    "warehouse_live_map_chunk_storage",
]
