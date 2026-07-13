"""Queue depth sampling from Redis broker."""

from __future__ import annotations

import logging

from backend.observability import prometheus_metrics

logger = logging.getLogger(__name__)


def refresh_queue_depth_metrics(broker_url: str | None = None) -> None:
    """Sample Redis list lengths for known Celery queues."""

    try:
        import redis
    except ImportError:
        return

    if not broker_url:
        from backend.core.config.runtime import settings

        broker_url = settings.celery_broker_url
    if not broker_url or not broker_url.startswith("redis"):
        return

    try:
        client = redis.Redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)
        try:
            for queue in prometheus_metrics.KNOWN_QUEUES:
                depth = int(client.llen(queue) or 0)
                prometheus_metrics.queue_depth.labels(queue=queue).set(depth)
                prometheus_metrics.redis_queue_depth.labels(queue_name=queue).set(depth)
        finally:
            client.close()
    except Exception as exc:
        logger.debug("Queue depth sampling skipped: %s", exc)
