from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import orjson

from backend.infrastructure.messaging.websocket_publisher._publisher_refs import publisher_module
from backend.infrastructure.messaging.websocket_publisher.constants import REDIS_CHANNEL
from backend.infrastructure.messaging.websocket_publisher.metrics import _record_telemetry_redis_fallback

logger = logging.getLogger(__name__)


class RedisFanoutMixin:
    """Redis pub/sub initialization and subscriber loop."""

    async def initialize(self):
        """Initialize Redis pub/sub fan-out if Redis is available."""
        from backend.core.config.runtime import settings

        try:
            import redis.asyncio as aioredis

            self._redis = await aioredis.from_url(settings.redis_url, decode_responses=False)
            await self._redis.ping()
            self._subscriber_task = asyncio.create_task(self._run_redis_subscriber())
            logger.info(
                "WebSocket manager: Redis pub/sub fan-out enabled (channel=%s)", REDIS_CHANNEL
            )
        except Exception as exc:
            _record_telemetry_redis_fallback("init_unavailable")
            logger.warning(
                "WebSocket manager: Redis unavailable, falling back to in-process broadcast: %s",
                exc,
            )
            self._redis = None

    async def _run_redis_subscriber(self) -> None:
        """Run the pub/sub listener with reconnect until shutdown."""
        backoff_s = 1.0
        while not self._shutting_down:
            try:
                await self._redis_subscriber()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._shutting_down:
                    break
                _record_telemetry_redis_fallback("subscriber_error")
                logger.error("Redis subscriber crashed: %s", exc)
            if self._shutting_down:
                break
            _record_telemetry_redis_fallback("subscriber_reconnect")
            logger.warning(
                "Redis subscriber exited unexpectedly; reconnecting in %.1fs",
                backoff_s,
            )
            await publisher_module().asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 30.0)

    async def _redis_subscriber(self):
        from backend.core.config.runtime import settings

        r = None
        pubsub = None
        try:
            import redis.asyncio as aioredis

            r = await aioredis.from_url(settings.redis_url, decode_responses=False)
            pubsub = r.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    raw = message["data"]
                    mission_runtime_id = None
                    org_id = None
                    payload = raw
                    try:
                        parsed = orjson.loads(raw)
                        if (
                            isinstance(parsed, dict)
                            and parsed.get("v") == 1
                            and "d" in parsed
                        ):
                            filt = parsed.get("f") or {}
                            mission_runtime_id = filt.get("m")
                            org_id = filt.get("o")
                            body = parsed["d"]
                            payload = (
                                body
                                if isinstance(body, (bytes, bytearray))
                                else orjson.dumps(body)
                            )
                    except Exception:
                        payload = raw
                    await self._local_broadcast(
                        payload,
                        mission_runtime_id=mission_runtime_id,
                        org_id=org_id,
                    )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            message = str(exc).lower()
            if self._shutting_down or "connection closed" in message:
                logger.info("Redis subscriber closed during shutdown: %s", exc)
            else:
                _record_telemetry_redis_fallback("subscriber_error")
                logger.error("Redis subscriber error: %s", exc)
        finally:
            if pubsub is not None:
                with suppress(Exception):
                    await pubsub.close()
            if r is not None:
                with suppress(Exception):
                    await r.aclose()

    async def shutdown(self) -> None:
        self._shutting_down = True
        task = self._subscriber_task
        self._subscriber_task = None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._redis is not None:
            with suppress(Exception):
                await self._redis.aclose()
            self._redis = None

