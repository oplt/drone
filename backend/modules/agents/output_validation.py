from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.modules.agents.schemas import AgentOutputType


class ValidatedAgentOutput(BaseModel):
    """Closed contract shared by the registered mission-agent output families."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    operator_message: str = Field(..., min_length=1, max_length=4000)
    risk_level: Literal["low", "medium", "high", "critical"] | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    requires_human_review: bool = False
    requires_human_approval: bool = False
    human_confirmation_required: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    abstained: bool = False
    decision_status: Literal[
        "confident",
        "no_evidence",
        "provider_unavailable",
        "input_stale",
        "model_uncertain",
    ] = "confident"

    # Warehouse scan
    scan_quality: Literal["excellent", "good", "partial", "poor"] | None = None
    coverage_summary: str | None = Field(default=None, max_length=4000)
    mapping_backend: str | None = Field(default=None, max_length=500)
    problems: list[str] = Field(default_factory=list, max_length=64)
    likely_causes: list[str] = Field(default_factory=list, max_length=64)
    recommended_next_scan: list[str] = Field(default_factory=list, max_length=64)

    # Field survey
    field_summary: str | None = Field(default=None, max_length=4000)
    coverage_quality: Literal["excellent", "good", "partial", "poor"] | None = None
    missing_areas: list[str] = Field(default_factory=list, max_length=64)
    possible_issues: list[str] = Field(default_factory=list, max_length=64)
    next_steps: list[str] = Field(default_factory=list, max_length=64)
    recommended_altitude_m: float | None = None
    recommended_speed_mps: float | None = None
    front_overlap_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    side_overlap_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    reasoning_summary: str | None = Field(default=None, max_length=4000)

    # Livestock
    route_summary: str | None = Field(default=None, max_length=4000)
    animals_detected: int | None = Field(default=None, ge=0)
    missing_expected_animals: int | None = Field(default=None, ge=0)
    risk_notes: list[str] = Field(default_factory=list, max_length=64)
    recommended_next_action: str | None = Field(default=None, max_length=2000)

    # Patrol
    incident_summary: str | None = Field(default=None, max_length=4000)
    confidence_explanation: str | None = Field(default=None, max_length=4000)
    false_positive_risk: Literal["low", "medium", "high"] | None = None
    recommended_action: str | None = Field(default=None, max_length=2000)

    # Warehouse inspection
    inspection_summary: str | None = Field(default=None, max_length=4000)
    missed_targets: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def normalize_risk(self) -> ValidatedAgentOutput:
        if self.risk_level is None and self.severity is not None:
            self.risk_level = self.severity
        if self.confidence is not None and self.confidence < 0.55:
            self.abstained = True
            self.requires_human_review = True
            if self.decision_status == "confident":
                self.decision_status = "model_uncertain"
        if self.decision_status != "confident":
            self.abstained = True
            self.requires_human_review = True
        action_text = " ".join(
            value
            for value in (self.recommended_action, self.recommended_next_action)
            if isinstance(value, str)
        ).lower()
        if re.search(
            r"\b(arm|takeoff|take off|land|rtl|return to launch|send mavlink|"
            r"change safety|disable (safety|failsafe|geofence|preflight)|"
            r"bypass (safety|failsafe|geofence|preflight))\b",
            action_text,
        ):
            self.requires_human_approval = True
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
