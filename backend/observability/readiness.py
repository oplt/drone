from __future__ import annotations

import asyncio
from typing import Any

from backend.core.config.runtime import settings


async def dependency_readiness() -> tuple[bool, dict[str, Any]]:
    broker_url = str(settings.celery_broker_url or "")
    if not broker_url.startswith(("redis://", "rediss://")):
        return False, {"redis_broker": {"ready": False, "error": "unsupported broker URL"}}

    try:
        import redis.asyncio as redis

        client = redis.from_url(
            broker_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            await asyncio.wait_for(client.ping(), timeout=1.5)
        finally:
            await client.aclose()
    except Exception as exc:
        return False, {
            "redis_broker": {
                "ready": False,
                "error": type(exc).__name__,
            }
        }
    return True, {"redis_broker": {"ready": True}}
