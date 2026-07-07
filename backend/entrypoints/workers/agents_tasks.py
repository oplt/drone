from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from sqlalchemy import select

from backend.core.database.session import Session
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.agents.context_builders import (
    build_field_survey_context,
    build_livestock_plan_context,
    build_patrol_incident_context,
    build_property_patrol_incident_context,
    build_warehouse_inspection_context,
    build_warehouse_scan_context,
)
from backend.modules.agents.schemas import AgentContext, AgentPhase, MissionAgentId
from backend.modules.agents.service import mission_agent_service
from backend.modules.patrol.models import PatrolIncident
from backend.modules.property_patrol.models import (
    PropertyPatrolIncident,
    PropertyPatrolTemplate,
)

logger = logging.getLogger(__name__)

_worker_loop = WorkerLoopState()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    return _worker_loop.get_loop()


def _run_on_worker_loop(coro: Coroutine[Any, Any, dict[str, Any]]) -> dict[str, Any]:
    loop = _get_worker_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _hydrate_context(db, agent_id: MissionAgentId, context: AgentContext) -> AgentContext:
    payload = dict(context.structured_payload)
    if agent_id == MissionAgentId.PRIVATE_PATROL and payload.get("patrol_incident_id"):
        payload.update(
            await build_patrol_incident_context(
                db, incident_id=int(payload["patrol_incident_id"])
            )
        )
    elif agent_id == MissionAgentId.PROPERTY_PATROL and payload.get("property_patrol_incident_id"):
        payload.update(
            await build_property_patrol_incident_context(
                db, incident_id=int(payload["property_patrol_incident_id"])
            )
        )
    elif agent_id == MissionAgentId.WAREHOUSE_SCAN and payload.get("warehouse_map_id"):
        payload.update(
            await build_warehouse_scan_context(
                db,
                warehouse_map_id=int(payload["warehouse_map_id"]),
                capture_result=payload.get("capture_result"),
                client_flight_id=context.client_flight_id,
            )
        )
    elif agent_id == MissionAgentId.WAREHOUSE_INSPECTION and payload.get("inspection_mission_id"):
        payload.update(
            await build_warehouse_inspection_context(
                db, inspection_mission_id=int(payload["inspection_mission_id"])
            )
        )
    elif agent_id == MissionAgentId.FIELD_SURVEY:
        payload.update(
            await build_field_survey_context(
                db,
                mission_runtime_id=context.mission_runtime_id,
                client_flight_id=context.client_flight_id,
                extra=payload,
            )
        )
    elif agent_id == MissionAgentId.LIVESTOCK and payload.get("livestock_task_id"):
        payload.update(
            await build_livestock_plan_context(
                db,
                task_id=int(payload["livestock_task_id"]),
                mission_plan=dict(payload.get("mission_plan") or {}),
            )
        )
    return context.model_copy(update={"structured_payload": payload})


async def _apply_side_effects(
    db,
    *,
    agent_id: MissionAgentId,
    context: AgentContext,
    result_text: str,
    structured: dict[str, Any] | None,
) -> None:
    if result_text and agent_id == MissionAgentId.PRIVATE_PATROL:
        incident_id = context.structured_payload.get("patrol_incident_id")
        if incident_id is not None:
            incident = await db.get(PatrolIncident, int(incident_id))
            if incident is not None:
                summary = dict(incident.summary or {})
                summary["llm_summary"] = result_text
                if structured:
                    summary["llm_structured"] = structured
                incident.summary = summary
                await db.flush()
    if result_text and agent_id == MissionAgentId.PROPERTY_PATROL:
        incident_id = context.structured_payload.get("property_patrol_incident_id")
        if incident_id is not None:
            incident = await db.get(PropertyPatrolIncident, int(incident_id))
            if incident is not None:
                incident.llm_summary = result_text
                await db.flush()


async def _execute_agent(agent_id: MissionAgentId, context: AgentContext) -> dict[str, Any]:
    async with Session() as db:
        hydrated = await _hydrate_context(db, agent_id, context)
        result = await mission_agent_service.run(agent_id, hydrated, db=db, persist=True)
        if result.status == "ok" and result.text:
            await _apply_side_effects(
                db,
                agent_id=agent_id,
                context=hydrated,
                result_text=result.text,
                structured=result.structured,
            )
        await db.commit()
        return result.model_dump(mode="json")


@celery_app.task(name="agents.run_agent_task", bind=True, max_retries=1)
def run_agent_task(self, *, agent_id: str, context: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = AgentContext.model_validate(context)
        return _run_on_worker_loop(_execute_agent(MissionAgentId(agent_id), parsed))
    except Exception as exc:
        logger.exception("Agent task failed for %s", agent_id)
        raise self.retry(exc=exc, countdown=5) from exc


@celery_app.task(name="agents.summarize_property_patrol_incident")
def summarize_property_patrol_incident(*, incident_id: int) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        async with Session() as db:
            incident = await db.get(PropertyPatrolIncident, incident_id)
            if incident is None:
                return {"status": "missing"}
            template = await db.scalar(
                select(PropertyPatrolTemplate)
                .where(PropertyPatrolTemplate.site_id == incident.site_id)
                .order_by(PropertyPatrolTemplate.updated_at.desc())
            )
            if template is not None and not template.llm_summary_enabled:
                return {"status": "disabled"}
        context = AgentContext(
            phase=AgentPhase.ON_EVENT,
            mission_type="property_patrol",
            structured_payload={"property_patrol_incident_id": incident_id},
        )
        return await _execute_agent(MissionAgentId.PROPERTY_PATROL, context)

    return _run_on_worker_loop(_run())
