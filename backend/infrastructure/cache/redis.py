"""Shared Redis client for application read-through caches."""

from __future__ import annotations

from typing import Any

from backend.core.config.runtime import settings

_client: Any | None = None
_sync_client: Any | None = None


def get_redis_client() -> Any:
    global _client
    if _client is None:
        import redis.asyncio as redis

        _client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    return _client


def get_sync_redis_client() -> Any:
    """Return the shared synchronous Redis client for sync adapters.

    A few legacy status readers are synchronous because they are called from
    Celery and thread adapters. They still use the shared Redis instance; they
    must never fall back to process-local authoritative state.
    """
    global _sync_client
    if _sync_client is None:
        import redis

        _sync_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    return _sync_client


def redis_available() -> bool:
    """Bounded liveness probe used before optional cache operations."""
    try:
        return bool(get_sync_redis_client().ping())
    except Exception:
        return False


def close_sync_redis_client() -> None:
    """Close the shared synchronous client from Celery/process shutdown hooks."""
    global _sync_client
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None


async def close_redis_client() -> None:
    global _client, _sync_client
    if _client is None:
        close_sync_redis_client()
        return
    await _client.aclose()
    _client = None
    close_sync_redis_client()
