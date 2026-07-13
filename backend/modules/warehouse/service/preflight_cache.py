from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.cache.local import BoundedTTLCache
from backend.infrastructure.cache.redis import get_redis_client, redis_available
from backend.observability.prometheus_metrics import warehouse_preflight_cache_serves_total

_PREFLIGHT_SNAPSHOT_CACHE = BoundedTTLCache[Any](max_entries=256)
_PREFLIGHT_SNAPSHOT_CACHE_LOCK = asyncio.Lock()
_PREFLIGHT_CACHE_PREFIX = "warehouse:preflight:snapshot:v1"


def preflight_snapshot_cache_ttl_s() -> float:
    return max(
        0.0,
        float(getattr(settings, "warehouse_preflight_snapshot_cache_ttl_s", 4.0)),
    )


def preflight_snapshot_cache_key(user_id: int, mission_loaded: bool) -> tuple[int, bool]:
    return (int(user_id), bool(mission_loaded))


def _redis_key(user_id: int, mission_loaded: bool) -> str:
    return f"{_PREFLIGHT_CACHE_PREFIX}:{int(user_id)}:{int(bool(mission_loaded))}"


def _snapshot_payload(snapshot: Any) -> str:
    value = snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else snapshot
    return json.dumps(value, separators=(",", ":"), default=str)


def _snapshot_from_payload(payload: str) -> Any:
    from backend.modules.warehouse.http_models import WarehousePreflightOut

    return WarehousePreflightOut.model_validate(json.loads(payload))


async def get_cached_preflight_snapshot(
    user_id: int,
    mission_loaded: bool,
) -> Any | None:
    ttl = preflight_snapshot_cache_ttl_s()
    if ttl <= 0.0:
        return None
    key = preflight_snapshot_cache_key(user_id, mission_loaded)
    try:
        if not redis_available():
            raise RuntimeError("shared cache unavailable")
        redis = get_redis_client()
        payload = await asyncio.wait_for(
            redis.get(_redis_key(user_id, mission_loaded)), timeout=0.25
        )
        if payload:
            warehouse_preflight_cache_serves_total.labels(state="hit").inc()
            return _snapshot_from_payload(payload)
    except Exception:
        # Local cache remains a bounded accelerator when Redis is unavailable.
        pass
    async with _PREFLIGHT_SNAPSHOT_CACHE_LOCK:
        cached = _PREFLIGHT_SNAPSHOT_CACHE.get(key, ttl_seconds=ttl)
        if cached is None:
            return None
    warehouse_preflight_cache_serves_total.labels(state="hit").inc()
    return cached


async def store_preflight_snapshot_cache(
    user_id: int,
    mission_loaded: bool,
    snapshot: Any,
) -> None:
    if preflight_snapshot_cache_ttl_s() <= 0.0:
        return
    key = preflight_snapshot_cache_key(user_id, mission_loaded)
    try:
        if not redis_available():
            raise RuntimeError("shared cache unavailable")
        redis = get_redis_client()
        await asyncio.wait_for(
            redis.setex(
                _redis_key(user_id, mission_loaded),
                max(1, int(preflight_snapshot_cache_ttl_s())),
                _snapshot_payload(snapshot),
            ),
            timeout=0.25,
        )
    except Exception:
        pass
    async with _PREFLIGHT_SNAPSHOT_CACHE_LOCK:
        _PREFLIGHT_SNAPSHOT_CACHE.set(key, snapshot)


async def clear_preflight_snapshot_cache() -> None:
    try:
        if not redis_available():
            raise RuntimeError("shared cache unavailable")
        redis = get_redis_client()
        async def _scan_keys() -> list[str]:
            return [
                key
                async for key in redis.scan_iter(match=f"{_PREFLIGHT_CACHE_PREFIX}:*")
            ]

        keys = await asyncio.wait_for(_scan_keys(), timeout=0.25)
        if keys:
            await asyncio.wait_for(redis.delete(*keys), timeout=0.25)
    except Exception:
        pass
    async with _PREFLIGHT_SNAPSHOT_CACHE_LOCK:
        _PREFLIGHT_SNAPSHOT_CACHE.clear()
