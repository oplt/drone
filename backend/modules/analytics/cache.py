"""Redis-backed analytics overview cache."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "analytics:overview"


def _key(org_id: int | None) -> str:
    return f"{_CACHE_PREFIX}:{org_id or 'global'}"


async def get_cached_overview(redis, org_id: int | None) -> dict | None:
    try:
        raw = await redis.get(_key(org_id))
        return json.loads(raw) if raw else None
    except Exception:
        logger.debug("analytics cache get failed", exc_info=True)
        return None


async def set_cached_overview(redis, org_id: int | None, data: dict, ttl: int = 60) -> None:
    try:
        await redis.set(_key(org_id), json.dumps(data), ex=ttl)
    except Exception:
        logger.debug("analytics cache set failed", exc_info=True)


async def invalidate_overview(redis, org_id: int | None) -> None:
    try:
        await redis.delete(_key(org_id))
    except Exception:
        logger.debug("analytics cache invalidate failed", exc_info=True)
