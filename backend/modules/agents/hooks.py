from __future__ import annotations

import logging
from typing import Any

from backend.modules.agents.registry import agents_for_mission_type
from backend.modules.agents.schemas import AgentContext, AgentPhase, MissionAgentId

logger = logging.getLogger(__name__)


def enqueue_agent_run(
    agent_id: MissionAgentId,
    context: AgentContext,
) -> None:
    """Best-effort enqueue; never raises to callers on the flight path."""
    try:
        from backend.entrypoints.workers.agents_tasks import run_agent_task

        run_agent_task.delay(
            agent_id=agent_id.value,
            context=context.model_dump(mode="json"),
        )
    except Exception:
        logger.exception("Failed to enqueue agent task for %s", agent_id)


def schedule_agent_hook(
    phase: AgentPhase,
    *,
    agent_id: MissionAgentId,
    mission_type: str | None = None,
    mission_runtime_id: int | None = None,
    client_flight_id: str | None = None,
    structured_payload: dict[str, Any] | None = None,
    question: str | None = None,
) -> None:
    context = AgentContext(
        mission_runtime_id=mission_runtime_id,
        mission_type=mission_type,
        client_flight_id=client_flight_id,
        phase=phase,
        question=question,
        structured_payload=structured_payload or {},
    )
    enqueue_agent_run(agent_id, context)


def schedule_postflight_for_mission_type(
    mission_type: str,
    *,
    mission_runtime_id: int | None = None,
    client_flight_id: str | None = None,
    structured_payload: dict[str, Any] | None = None,
) -> None:
    for agent_id in agents_for_mission_type(mission_type):
        schedule_agent_hook(
            AgentPhase.POSTFLIGHT,
            agent_id=agent_id,
            mission_type=mission_type,
            mission_runtime_id=mission_runtime_id,
            client_flight_id=client_flight_id,
            structured_payload=structured_payload,
        )


def schedule_patrol_incident_summary(*, incident_id: int, created: bool) -> None:
    if not created:
        return
    schedule_agent_hook(
        AgentPhase.ON_EVENT,
        agent_id=MissionAgentId.PRIVATE_PATROL,
        mission_type="private_patrol",
        structured_payload={"patrol_incident_id": incident_id},
    )


def schedule_property_patrol_incident_summary(*, incident_id: int) -> None:
    schedule_agent_hook(
        AgentPhase.ON_EVENT,
        agent_id=MissionAgentId.PROPERTY_PATROL,
        mission_type="property_patrol",
        structured_payload={"property_patrol_incident_id": incident_id},
    )


def schedule_warehouse_scan_postflight(
    *,
    warehouse_map_id: int,
    client_flight_id: str | None,
    capture_result: dict[str, Any],
) -> None:
    schedule_agent_hook(
        AgentPhase.POSTFLIGHT,
        agent_id=MissionAgentId.WAREHOUSE_SCAN,
        mission_type="warehouse_scan",
        client_flight_id=client_flight_id,
        structured_payload={
            "warehouse_map_id": warehouse_map_id,
            "capture_result": capture_result,
        },
    )


def schedule_warehouse_inspection_postflight(*, inspection_mission_id: int) -> None:
    schedule_agent_hook(
        AgentPhase.POSTFLIGHT,
        agent_id=MissionAgentId.WAREHOUSE_INSPECTION,
        mission_type="warehouse_inspection",
        structured_payload={"inspection_mission_id": inspection_mission_id},
    )


def schedule_livestock_plan_narrative(
    *,
    task_id: int,
    mission_plan: dict[str, Any],
) -> None:
    schedule_agent_hook(
        AgentPhase.PLAN,
        agent_id=MissionAgentId.LIVESTOCK,
        mission_type="livestock",
        structured_payload={
            "livestock_task_id": task_id,
            "mission_plan": mission_plan,
        },
    )
