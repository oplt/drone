from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from celery.signals import worker_shutdown

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.agents.llm import close_ai_gateway
from backend.modules.agents.schemas import AgentContext, MissionAgentId
from backend.modules.agents.worker_service import execute_agent
from backend.modules.agents.worker_service import (
    summarize_property_patrol_incident as summarize_incident,
)

logger = logging.getLogger(__name__)

_worker_loop = WorkerLoopState()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    return _worker_loop.get_loop()


def _run_on_worker_loop(coro: Coroutine[Any, Any, Any]) -> Any:
    loop = _get_worker_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@worker_shutdown.connect
def _agents_worker_shutdown(sender: Any = None, **_kwargs: Any) -> None:
    del sender
    try:
        _run_on_worker_loop(close_ai_gateway())
    except Exception:
        logger.debug("AI gateway shutdown cleanup failed", exc_info=True)


@celery_app.task(name="agents.run_agent_task", bind=True, max_retries=1)
def run_agent_task(self, *, agent_id: str, context: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = AgentContext.model_validate(context)
        return _run_on_worker_loop(execute_agent(MissionAgentId(agent_id), parsed))
    except Exception as exc:
        logger.exception("Agent task failed for %s", agent_id)
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries, max_seconds=120),
        ) from exc


@celery_app.task(name="agents.summarize_property_patrol_incident")
def summarize_property_patrol_incident(*, incident_id: int) -> dict[str, Any]:
    return _run_on_worker_loop(summarize_incident(incident_id=incident_id))
