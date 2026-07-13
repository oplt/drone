"""Redis-backed analytics overview cache."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from backend.observability import prometheus_metrics

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "analytics:overview:v1"


def _key(org_id: int) -> str:
    return f"{_CACHE_PREFIX}:org:{org_id}"


async def get_cached_overview(redis: Any, org_id: int | None) -> dict | None:
    if org_id is None:
        return None
    started = time.perf_counter()
    try:
        raw = await redis.get(_key(org_id))
        if not raw:
            prometheus_metrics.cache_misses_total.labels(cache="analytics_overview").inc()
            return None
        value = json.loads(raw)
        if not isinstance(value, dict):
            prometheus_metrics.cache_misses_total.labels(cache="analytics_overview").inc()
            return None
        prometheus_metrics.cache_hits_total.labels(cache="analytics_overview").inc()
        return value
    except Exception:
        prometheus_metrics.cache_misses_total.labels(cache="analytics_overview").inc()
        logger.debug("analytics cache get failed", exc_info=True)
        return None
    finally:
        prometheus_metrics.analytics_overview_cache_latency_seconds.labels(
            operation="get"
        ).observe(time.perf_counter() - started)


async def set_cached_overview(redis: Any, org_id: int | None, data: dict, ttl: int = 60) -> None:
    if org_id is None:
        return
    started = time.perf_counter()
    try:
        await redis.set(_key(org_id), json.dumps(data), ex=ttl)
    except Exception:
        logger.debug("analytics cache set failed", exc_info=True)
    finally:
        prometheus_metrics.analytics_overview_cache_latency_seconds.labels(
            operation="set"
        ).observe(time.perf_counter() - started)


async def invalidate_overview(redis: Any, org_id: int | None) -> None:
    if org_id is None:
        return
    started = time.perf_counter()
    try:
        await redis.delete(_key(org_id))
    except Exception:
        logger.debug("analytics cache invalidate failed", exc_info=True)
    finally:
        prometheus_metrics.analytics_overview_cache_latency_seconds.labels(
            operation="invalidate"
        ).observe(time.perf_counter() - started)
