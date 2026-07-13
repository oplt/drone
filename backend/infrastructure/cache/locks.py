"""Redis-backed distributed locks with a safe development fallback."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from backend.infrastructure.cache.redis import get_redis_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def distributed_lock(
    name: str, *, timeout: int = 900, blocking_timeout: float = 2.0
) -> AsyncIterator[None]:
    redis = get_redis_client()
    if redis is None:
        yield
        return
    try:
        lock = redis.lock(name, timeout=timeout, blocking_timeout=blocking_timeout)
        acquired = await lock.acquire()
    except Exception:
        # Redis is coordination, not authoritative storage. Preserve service
        # availability when the optional lock backend is temporarily down.
        logger.warning("Distributed lock backend unavailable: %s", name, exc_info=True)
        yield
        return
    if not acquired:
        raise TimeoutError(f"Could not acquire distributed lock: {name}")
    try:
        yield
    finally:
        with suppress(Exception):
            await lock.release()
