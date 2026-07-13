"""Small deterministic AI regression harness for prompt/model changes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from backend.modules.agents.repository import redact_audit_value


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    prompt_version: str
    input: dict[str, Any]
    expected: dict[str, Any]
    requires_human_approval: bool = False


class EvaluationResult(BaseModel):
    case_id: str
    prompt_version: str
    passed: bool
    grounded: bool
    abstained: bool
    confidence: float | None = None
    redacted_output: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None


def evaluate_case(
    case: EvaluationCase,
    output: dict[str, Any],
    *,
    grounding_check: Callable[[dict[str, Any]], bool] | None = None,
) -> EvaluationResult:
    confidence = output.get("confidence")
    confidence_value = float(confidence) if isinstance(confidence, (float, int)) else None
    abstained = bool(output.get("abstained")) or (
        confidence_value is not None and confidence_value < 0.55
    )
    grounded = grounding_check(output) if grounding_check else True
    required_match = all(output.get(key) == value for key, value in case.expected.items())
    approved = not case.requires_human_approval or bool(
        output.get("requires_human_approval") or output.get("human_confirmation_required")
    )
    passed = required_match and grounded and approved
    return EvaluationResult(
        case_id=case.case_id,
        prompt_version=case.prompt_version,
        passed=passed,
        grounded=grounded,
        abstained=abstained,
        confidence=confidence_value,
        redacted_output=redact_audit_value(output),
        failure_reason=None
        if passed
        else "expectation, grounding, or approval policy failed",
    )
