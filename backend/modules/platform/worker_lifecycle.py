"""Worker shutdown hooks kept behind the entrypoint/application boundary."""

from __future__ import annotations


def close_worker_cache_clients() -> None:
    from backend.infrastructure.cache.redis import close_sync_redis_client

    close_sync_redis_client()
