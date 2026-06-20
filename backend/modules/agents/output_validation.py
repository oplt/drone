from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.modules.agents.schemas import AgentOutputType


class ValidatedAgentOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    operator_message: str = Field(..., min_length=1, max_length=4000)
    risk_level: Literal["low", "medium", "high", "critical"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    requires_human_review: bool = False
    requires_human_approval: bool = False
    human_confirmation_required: bool = False

    @model_validator(mode="after")
    def normalize_risk(self) -> ValidatedAgentOutput:
        if self.risk_level is None and self.severity is not None:
            self.risk_level = self.severity
        return self


def validate_agent_output(
    output_type: AgentOutputType,
    structured: dict[str, Any] | None,
) -> ValidatedAgentOutput:
    if structured is None:
        raise ValueError("Agent response must be a JSON object")
    validated = ValidatedAgentOutput.model_validate(structured)
    if output_type == AgentOutputType.MISSION_DRAFT:
        validated.requires_human_approval = True
    return validated
