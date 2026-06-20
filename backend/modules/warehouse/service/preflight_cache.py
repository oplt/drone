from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.core.config.runtime import settings
from backend.observability.prometheus_metrics import warehouse_preflight_cache_serves_total

_PREFLIGHT_SNAPSHOT_CACHE: dict[tuple[int, bool], tuple[float, Any]] = {}
_PREFLIGHT_SNAPSHOT_CACHE_LOCK = asyncio.Lock()


def preflight_snapshot_cache_ttl_s() -> float:
    return max(
        0.0,
        float(getattr(settings, "warehouse_preflight_snapshot_cache_ttl_s", 4.0)),
    )


def preflight_snapshot_cache_key(user_id: int, mission_loaded: bool) -> tuple[int, bool]:
    return (int(user_id), bool(mission_loaded))


async def get_cached_preflight_snapshot(
    user_id: int,
    mission_loaded: bool,
) -> Any | None:
    ttl = preflight_snapshot_cache_ttl_s()
    if ttl <= 0.0:
        return None
    key = preflight_snapshot_cache_key(user_id, mission_loaded)
    async with _PREFLIGHT_SNAPSHOT_CACHE_LOCK:
        cached = _PREFLIGHT_SNAPSHOT_CACHE.get(key)
        if cached is None:
            return None
        cached_at, snapshot = cached
        if (time.monotonic() - cached_at) > ttl:
            _PREFLIGHT_SNAPSHOT_CACHE.pop(key, None)
            return None
    warehouse_preflight_cache_serves_total.labels(state="hit").inc()
    return snapshot


async def store_preflight_snapshot_cache(
    user_id: int,
    mission_loaded: bool,
    snapshot: Any,
) -> None:
    if preflight_snapshot_cache_ttl_s() <= 0.0:
        return
    key = preflight_snapshot_cache_key(user_id, mission_loaded)
    async with _PREFLIGHT_SNAPSHOT_CACHE_LOCK:
        _PREFLIGHT_SNAPSHOT_CACHE[key] = (time.monotonic(), snapshot)


async def clear_preflight_snapshot_cache() -> None:
    async with _PREFLIGHT_SNAPSHOT_CACHE_LOCK:
        _PREFLIGHT_SNAPSHOT_CACHE.clear()
