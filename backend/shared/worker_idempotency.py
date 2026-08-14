"""Sync Redis idempotency guards for Celery worker tasks."""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Any

from backend.infrastructure.cache.redis import get_sync_redis_client

logger = logging.getLogger(__name__)

_PREFIX = "worker:idempotency"


class WorkerTaskClaim(StrEnum):
    EXECUTE = "execute"
    SKIP_COMPLETED = "skip_completed"
    SKIP_IN_FLIGHT = "skip_in_flight"


def _redis_key(namespace: str, idempotency_key: str) -> str:
    return f"{_PREFIX}:{namespace}:{idempotency_key}"


def claim_worker_task(
    namespace: str,
    idempotency_key: str,
    *,
    ttl_s: int = 7200,
) -> tuple[WorkerTaskClaim, dict[str, Any] | None]:
    """Return whether this worker invocation should execute and any cached result."""
    redis_key = _redis_key(namespace, idempotency_key)
    try:
        client = get_sync_redis_client()
        raw = client.get(redis_key)
        if raw:
            payload = json.loads(raw)
            state = payload.get("state")
            if state == "completed":
                return WorkerTaskClaim.SKIP_COMPLETED, payload.get("result")
            if state == "running":
                return WorkerTaskClaim.SKIP_IN_FLIGHT, None
        if client.set(
            redis_key,
            json.dumps({"state": "running"}),
            nx=True,
            ex=max(60, int(ttl_s)),
        ):
            return WorkerTaskClaim.EXECUTE, None
        raw = client.get(redis_key)
        if raw:
            payload = json.loads(raw)
            if payload.get("state") == "completed":
                return WorkerTaskClaim.SKIP_COMPLETED, payload.get("result")
        return WorkerTaskClaim.SKIP_IN_FLIGHT, None
    except Exception:
        logger.warning(
            "Worker idempotency claim failed for %s:%s",
            namespace,
            idempotency_key,
            exc_info=True,
        )
        return WorkerTaskClaim.EXECUTE, None


def complete_worker_task(
    namespace: str,
    idempotency_key: str,
    result: dict[str, Any],
    *,
    ttl_s: int = 7200,
) -> None:
    try:
        get_sync_redis_client().setex(
            _redis_key(namespace, idempotency_key),
            max(60, int(ttl_s)),
            json.dumps({"state": "completed", "result": result}, default=str),
        )
    except Exception:
        logger.debug("Worker idempotency complete failed", exc_info=True)


def release_worker_task(namespace: str, idempotency_key: str) -> None:
    """Drop a running claim so Celery retries can execute again."""
    redis_key = _redis_key(namespace, idempotency_key)
    try:
        client = get_sync_redis_client()
        raw = client.get(redis_key)
        if not raw:
            return
        payload = json.loads(raw)
        if payload.get("state") == "running":
            client.delete(redis_key)
    except Exception:
        logger.debug("Worker idempotency release failed", exc_info=True)
