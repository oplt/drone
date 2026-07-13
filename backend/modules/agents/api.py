from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.core.database.session import get_db
from backend.core.errors.public import public_error
from backend.modules.agents.context_builders import (
    build_field_survey_context,
    build_warehouse_inspection_context,
    build_warehouse_scan_context,
)
from backend.modules.agents.registry import get, list_agents
from backend.modules.agents.repository import AgentRunRepository
from backend.modules.agents.schemas import (
    AgentContext,
    AgentResult,
    AgentRunOut,
    AgentRunRequest,
    MissionAgentId,
)
from backend.modules.agents.service import mission_agent_service
from backend.modules.identity.dependencies import require_user

router = APIRouter(prefix="/api/ai/agents", tags=["agents"])


@router.get("/")
async def list_agent_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": definition.id.value,
            "llm_task": definition.llm_task,
            "supported_phases": [phase.value for phase in definition.supported_phases],
            "prompt_version": definition.prompt_version,
        }
        for definition in list_agents()
    ]


@router.get("/runs", response_model=list[AgentRunOut])
async def list_agent_runs(
    mission_runtime_id: int = Query(..., ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Any = Depends(get_db),
    _user: Any = Depends(require_user),
) -> list[AgentRunOut]:
    rows = await AgentRunRepository().list_for_mission(
        db, mission_runtime_id=mission_runtime_id, limit=limit
    )
    return [AgentRunRepository.to_out(row) for row in rows]


@router.post("/{agent_id}/run", response_model=AgentResult)
async def run_agent_on_demand(
    agent_id: MissionAgentId,
    payload: AgentRunRequest,
    db: Any = Depends(get_db),
    user: Any = Depends(require_user),
) -> AgentResult:
    try:
        get(agent_id)
    except KeyError as exc:
        raise public_error(404, "AGENT_NOT_FOUND", "Agent definition not found") from exc

    structured = dict(payload.structured_payload)
    if payload.warehouse_map_id is not None:
        structured["warehouse_map_id"] = payload.warehouse_map_id
        structured.update(
            await build_warehouse_scan_context(
                db,
                warehouse_map_id=payload.warehouse_map_id,
                client_flight_id=payload.client_flight_id,
            )
        )
    if payload.inspection_mission_id is not None:
        structured["inspection_mission_id"] = payload.inspection_mission_id
        structured.update(
            await build_warehouse_inspection_context(
                db, inspection_mission_id=payload.inspection_mission_id
            )
        )
    if payload.patrol_incident_id is not None:
        structured["patrol_incident_id"] = payload.patrol_incident_id
    if payload.property_patrol_incident_id is not None:
        structured["property_patrol_incident_id"] = payload.property_patrol_incident_id
    if payload.livestock_task_id is not None:
        structured["livestock_task_id"] = payload.livestock_task_id
    if payload.mission_runtime_id is not None or payload.client_flight_id:
        structured.update(
            await build_field_survey_context(
                db,
                mission_runtime_id=payload.mission_runtime_id,
                client_flight_id=payload.client_flight_id,
            )
        )

    context = AgentContext(
        mission_runtime_id=payload.mission_runtime_id,
        mission_type=payload.mission_type,
        client_flight_id=payload.client_flight_id,
        user_id=int(user.id),
        org_id=getattr(user, "org_id", None),
        phase=payload.phase,
        question=payload.question,
        structured_payload=structured,
    )
    result = await mission_agent_service.run(agent_id, context, db=db, persist=True)
    await db.commit()
    if result.status == "error":
        raise public_error(503, "AGENT_UNAVAILABLE", "Agent run could not be completed")
    return result
