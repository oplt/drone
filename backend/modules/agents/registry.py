from __future__ import annotations

from backend.modules.agents.schemas import (
    AgentDefinition,
    AgentOutputType,
    AgentPhase,
    MissionAgentId,
)
from backend.modules.missions.schemas.mission_types import MissionType

_REGISTRY: dict[MissionAgentId, AgentDefinition] = {}


def register(definition: AgentDefinition) -> None:
    _REGISTRY[definition.id] = definition


def get(agent_id: MissionAgentId) -> AgentDefinition:
    if agent_id not in _REGISTRY:
        raise KeyError(f"Unknown agent: {agent_id}")
    return _REGISTRY[agent_id]


def list_agents() -> list[AgentDefinition]:
    return list(_REGISTRY.values())


def agents_for_mission_type(mission_type: str) -> list[MissionAgentId]:
    mapping: dict[str, list[MissionAgentId]] = {
        MissionType.WAREHOUSE_SCAN.value: [MissionAgentId.WAREHOUSE_SCAN],
        "warehouse_scan": [MissionAgentId.WAREHOUSE_SCAN],
        MissionType.WAREHOUSE_INSPECTION.value: [MissionAgentId.WAREHOUSE_INSPECTION],
        "warehouse_inspection": [MissionAgentId.WAREHOUSE_INSPECTION],
        MissionType.GRID.value: [MissionAgentId.FIELD_SURVEY],
        "grid": [MissionAgentId.FIELD_SURVEY],
        MissionType.PHOTOGRAMMETRY.value: [MissionAgentId.FIELD_SURVEY],
        "photogrammetry": [MissionAgentId.FIELD_SURVEY],
        MissionType.PRIVATE_PATROL.value: [MissionAgentId.PRIVATE_PATROL],
        "private_patrol": [MissionAgentId.PRIVATE_PATROL],
        MissionType.PERIMETER_PATROL.value: [MissionAgentId.PRIVATE_PATROL],
        "perimeter_patrol": [MissionAgentId.PRIVATE_PATROL],
        "property_patrol": [MissionAgentId.PROPERTY_PATROL],
    }
    return mapping.get(str(mission_type), [])


def _register_defaults() -> None:
    register(
        AgentDefinition(
            id=MissionAgentId.PRIVATE_PATROL,
            llm_task="private_patrol",
            prompt_template_path="private_patrol_v1.md",
            output_type=AgentOutputType.INCIDENT_SUMMARY,
            supported_phases=[AgentPhase.ON_EVENT, AgentPhase.POSTFLIGHT, AgentPhase.ON_DEMAND],
            settings_flag="private_patrol",
        )
    )
    register(
        AgentDefinition(
            id=MissionAgentId.PROPERTY_PATROL,
            llm_task="private_patrol",
            prompt_template_path="private_patrol_v1.md",
            output_type=AgentOutputType.INCIDENT_SUMMARY,
            supported_phases=[AgentPhase.ON_EVENT, AgentPhase.ON_DEMAND],
            settings_flag="private_patrol",
        )
    )
    register(
        AgentDefinition(
            id=MissionAgentId.WAREHOUSE_SCAN,
            llm_task="warehouse_scan",
            prompt_template_path="warehouse_scan_v1.md",
            output_type=AgentOutputType.POSTFLIGHT_REPORT,
            supported_phases=[AgentPhase.POSTFLIGHT, AgentPhase.ON_DEMAND],
            settings_flag="warehouse_scan",
        )
    )
    register(
        AgentDefinition(
            id=MissionAgentId.WAREHOUSE_INSPECTION,
            llm_task="warehouse_inspection",
            prompt_template_path="warehouse_inspection_v1.md",
            output_type=AgentOutputType.POSTFLIGHT_REPORT,
            supported_phases=[AgentPhase.POSTFLIGHT, AgentPhase.ON_DEMAND],
            settings_flag="warehouse_inspection",
        )
    )
    register(
        AgentDefinition(
            id=MissionAgentId.FIELD_SURVEY,
            llm_task="field_survey",
            prompt_template_path="field_survey_v1.md",
            output_type=AgentOutputType.POSTFLIGHT_REPORT,
            supported_phases=[AgentPhase.PLAN, AgentPhase.POSTFLIGHT, AgentPhase.ON_DEMAND],
            settings_flag="field_survey",
        )
    )
    register(
        AgentDefinition(
            id=MissionAgentId.LIVESTOCK,
            llm_task="livestock",
            prompt_template_path="livestock_v1.md",
            output_type=AgentOutputType.PARAMETER_ADVICE,
            supported_phases=[AgentPhase.PLAN, AgentPhase.POSTFLIGHT, AgentPhase.ON_DEMAND],
            settings_flag="livestock",
        )
    )
    register(
        AgentDefinition(
            id=MissionAgentId.ASSISTANT,
            llm_task="assistant",
            prompt_template_path="private_patrol_v1.md",
            output_type=AgentOutputType.ERROR_EXPLANATION,
            supported_phases=[AgentPhase.ON_DEMAND],
            settings_flag="assistant",
        )
    )


_register_defaults()
