from __future__ import annotations

import logging
from typing import Any

from celery.signals import worker_shutdown

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.agents.idempotency import derive_agent_idempotency_key
from backend.modules.agents.llm import close_ai_gateway
from backend.modules.agents.schemas import AgentContext, MissionAgentId
from backend.modules.agents.worker_service import execute_agent
from backend.modules.agents.worker_service import (
    summarize_property_patrol_incident as summarize_incident,
)
from backend.shared.worker_idempotency import (
    WorkerTaskClaim,
    claim_worker_task,
    complete_worker_task,
    release_worker_task,
)

logger = logging.getLogger(__name__)

_worker_loop = WorkerLoopState()


@worker_shutdown.connect
def _agents_worker_shutdown(sender: Any = None, **_kwargs: Any) -> None:
    del sender
    try:
        _worker_loop.run(close_ai_gateway())
    except Exception:
        logger.debug("AI gateway shutdown cleanup failed", exc_info=True)


@celery_app.task(
    name="agents.run_agent_task",
    bind=True,
    max_retries=1,
    time_limit=600,
    soft_time_limit=540,
)
def run_agent_task(self, *, agent_id: str, context: dict[str, Any]) -> dict[str, Any]:
    parsed = AgentContext.model_validate(context)
    agent = MissionAgentId(agent_id)
    idempotency_key = derive_agent_idempotency_key(agent, parsed)
    claim, cached = claim_worker_task("agents", idempotency_key, ttl_s=3600)
    if claim == WorkerTaskClaim.SKIP_COMPLETED and cached is not None:
        return cached
    if claim == WorkerTaskClaim.SKIP_IN_FLIGHT:
        return {"status": "duplicate", "idempotency_key": idempotency_key}
    try:
        result = _worker_loop.run(execute_agent(agent, parsed))
        if result.get("status") != "error":
            complete_worker_task("agents", idempotency_key, result, ttl_s=3600)
        else:
            release_worker_task("agents", idempotency_key)
        return result
    except Exception as exc:
        release_worker_task("agents", idempotency_key)
        logger.exception("Agent task failed for %s", agent_id)
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries, max_seconds=120),
        ) from exc


@celery_app.task(
    name="agents.summarize_property_patrol_incident",
    time_limit=600,
    soft_time_limit=540,
)
def summarize_property_patrol_incident(*, incident_id: int) -> dict[str, Any]:
    return _worker_loop.run(summarize_incident(incident_id=incident_id))
