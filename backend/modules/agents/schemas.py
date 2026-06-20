from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.modules.ai.schemas import LLMTaskName


class MissionAgentId(StrEnum):
    WAREHOUSE_SCAN = "warehouse_scan"
    WAREHOUSE_INSPECTION = "warehouse_inspection"
    FIELD_SURVEY = "field_survey"
    PRIVATE_PATROL = "private_patrol"
    PROPERTY_PATROL = "property_patrol"
    LIVESTOCK = "livestock"
    MISSION_PLANNER = "mission_planner"
    ASSISTANT = "assistant"


class AgentPhase(StrEnum):
    PLAN = "plan"
    PREFLIGHT = "preflight"
    INFLIGHT = "inflight"
    POSTFLIGHT = "postflight"
    ON_DEMAND = "on_demand"
    ON_EVENT = "on_event"


class AgentOutputType(StrEnum):
    INCIDENT_SUMMARY = "incident_summary"
    POSTFLIGHT_REPORT = "postflight_report"
    PREFLIGHT_EXPLANATION = "preflight_explanation"
    MISSION_DRAFT = "mission_draft"
    PARAMETER_ADVICE = "parameter_advice"
    ERROR_EXPLANATION = "error_explanation"


class AgentContext(BaseModel):
    mission_runtime_id: int | None = None
    mission_type: str | None = None
    client_flight_id: str | None = None
    org_id: int | None = None
    user_id: int | None = None
    phase: AgentPhase
    question: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    agent_id: MissionAgentId
    phase: AgentPhase
    output_type: AgentOutputType = AgentOutputType.POSTFLIGHT_REPORT
    text: str
    structured: dict[str, Any] | None = None
    risk_level: Literal["low", "medium", "high", "critical"] | None = None
    requires_human_approval: bool = False
    profile_id: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    prompt_version: str = "v1"
    status: Literal["ok", "skipped", "error"] = "ok"
    error_message: str | None = None


class AgentDefinition(BaseModel):
    id: MissionAgentId
    llm_task: LLMTaskName
    prompt_template_path: str
    output_type: AgentOutputType = AgentOutputType.POSTFLIGHT_REPORT
    supported_phases: list[AgentPhase] = Field(default_factory=list)
    prompt_version: str = "v1"
    max_turns: int = 1
    timeout_seconds: int = 30
    settings_flag: str = ""


class AgentRunRequest(BaseModel):
    phase: AgentPhase = AgentPhase.ON_DEMAND
    question: str | None = None
    mission_runtime_id: int | None = None
    client_flight_id: str | None = None
    mission_type: str | None = None
    warehouse_map_id: int | None = None
    inspection_mission_id: int | None = None
    patrol_incident_id: int | None = None
    property_patrol_incident_id: int | None = None
    livestock_task_id: int | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class AgentRunOut(BaseModel):
    id: int
    agent_id: str
    phase: str
    llm_task: str
    profile_id: str | None = None
    model: str | None = None
    prompt_version: str
    response_preview: str | None = None
    structured_result: dict[str, Any] | None = None
    latency_ms: int | None = None
    status: str
    error_message: str | None = None
    mission_runtime_id: int | None = None
    created_at: str | None = None
