"""Small async Redis-backed fixed-window limiter with safe local fallback."""

from __future__ import annotations

import asyncio
import time
from threading import Lock

from fastapi import HTTPException

from backend.infrastructure.cache.redis import get_redis_client

_LOCAL_COUNTS: dict[str, tuple[int, float]] = {}
_LOCAL_LOCK = Lock()


async def enforce_rate_limit(*, key: str, limit: int, window_seconds: int) -> None:
    """Raise 429 when a caller exceeds a bounded agriculture operation budget."""
    if limit <= 0:
        return
    bucket = int(time.time()) // max(1, window_seconds)
    redis_key = f"rate:{key}:{bucket}"
    try:
        redis = get_redis_client()
        count = int(await asyncio.wait_for(redis.incr(redis_key), timeout=0.25))
        if count == 1:
            await asyncio.wait_for(redis.expire(redis_key, max(1, window_seconds + 1)), timeout=0.25)
    except Exception:
        now = time.time()
        with _LOCAL_LOCK:
            current, expires_at = _LOCAL_COUNTS.get(key, (0, now + window_seconds))
            if now >= expires_at:
                current, expires_at = 0, now + window_seconds
            count = current + 1
            _LOCAL_COUNTS[key] = (count, expires_at)
    if count > limit:
        raise HTTPException(status_code=429, detail={"code": "AGRICULTURE_RATE_LIMITED", "retry_after_seconds": max(1, window_seconds - (int(time.time()) % window_seconds))}, headers={"Retry-After": str(max(1, window_seconds - (int(time.time()) % window_seconds)))})
