"""Bounded agriculture assistant: validated evidence in, auditable text out."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.ai.base import LLMMessage
from backend.modules.agents.llm import chat_with_task
from backend.modules.agents.repository import redact_audit_value
from backend.modules.agriculture.governance_models import AgricultureAssistantRun
from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureFieldProfile, AgricultureFlight, AgricultureObservation
from backend.modules.agriculture.p4_models import AgricultureCropRisk, AgricultureGrowthMetric, AgricultureGrowthStageEstimate
from backend.modules.agriculture.p5_models import AgricultureAgronomyRule, AgricultureGovernanceAudit
from backend.modules.agriculture.sensor_models import AgricultureFusionResult

PROMPT_VERSION = "agriculture_governance_v1"
GOVERNANCE_PROMPT = (Path(__file__).resolve().parents[1] / "agents" / "prompts" / "agriculture_governance_v1.md").read_text(encoding="utf-8")
_INJECTION_RE = re.compile(r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)|(?:system|developer)\s+(?:message|prompt)|tool\s*call|execute\s+(?:this|the)|override\s+(?:policy|rule|safety)|reveal\s+(?:the\s+)?prompt", re.I)
_UNSAFE_RECOMMENDATION_RE = re.compile(r"\b(?:apply|spray|dose|rate|mix|fertili[sz]e|herbicide|pesticide|fungicide|chemical|insecticide)\b", re.I)
_SECRET_TEXT_RE = re.compile(r"\b(?:api[_ -]?key|token|password|secret|authorization)\s*[:=]\s*\S+", re.I)


class PromptInjectionBlocked(ValueError):
    code = "prompt_injection_blocked"


class AgricultureAssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    summary: str = Field(..., min_length=1, max_length=2400)
    key_points: list[str] = Field(default_factory=list, max_length=12)
    next_steps: list[str] = Field(default_factory=list, max_length=12)
    cited_source_ids: list[str] = Field(default_factory=list, max_length=64)
    risk_level: Literal["low", "medium", "high", "critical"] = "high"
    confidence: float = Field(default=0.0, ge=0, le=1)
    human_approval_required: bool = True
    abstained: bool = False
    decision_status: Literal["confident", "no_evidence", "provider_unavailable", "input_stale", "model_uncertain"] = "confident"
    limitations: list[str] = Field(default_factory=list, max_length=12)


def sanitize_question(question: str) -> str:
    value = _SECRET_TEXT_RE.sub("[REDACTED_SECRET]", " ".join(question.replace("\x00", " ").split()))[:4000]
    if not value:
        return "Summarize the validated agriculture evidence."
    if _INJECTION_RE.search(value):
        raise PromptInjectionBlocked("Uploaded/operator text contained an instruction-like pattern")
    return value


def _checksum(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _citation(source_id: str, source_type: str, created_at: datetime | None, fields: list[str]) -> dict[str, Any]:
    return {"source_id": source_id, "source_type": source_type, "timestamp": created_at.isoformat() if created_at else None, "fields": fields}


def evaluate_deterministic_rules(evidence: list[dict[str, Any]], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate only approved rules; no model-generated thresholds or rates."""
    results: list[dict[str, Any]] = []
    for item in evidence:
        for rule in rules:
            params = rule.get("parameters") or {}
            if rule.get("issue_type") not in {"*", item.get("issue_type")}:
                continue
            if rule.get("crop_type") and rule["crop_type"] != item.get("crop_type"):
                continue
            if float(item.get("severity", 0)) < float(params.get("severity_min", 0)):
                continue
            if float(item.get("confidence", 0)) < float(params.get("confidence_min", 0)):
                continue
            result = {
                "rule_id": rule["id"], "rule_key": rule["rule_key"], "rule_version": rule["version"],
                "source_id": item["source_id"], "issue_type": item["issue_type"],
                "urgency": str(params.get("urgency", "medium")),
                "required_inspection": bool(params.get("required_inspection", True)),
                "action_kind": rule.get("action_kind", "inspection_only"),
                "jurisdiction": rule.get("jurisdiction"),
                "regulatory_reference": rule.get("regulatory_reference"),
            }
            if result["action_kind"] != "inspection_only":
                result["human_approval_required"] = True
            results.append(result)
    return results


class AgricultureGovernanceService:
    async def build_context(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight) -> dict[str, Any]:
        observations = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == run.id, AgricultureObservation.review_state == "confirmed").order_by(AgricultureObservation.created_at.asc()))).all())
        risks = list((await db.scalars(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == run.id, AgricultureCropRisk.review_state == "confirmed").order_by(AgricultureCropRisk.created_at.asc()))).all())
        profile = await db.scalar(select(AgricultureFieldProfile).where(AgricultureFieldProfile.field_id == flight.field_id))
        rules = list((await db.scalars(select(AgricultureAgronomyRule).where(AgricultureAgronomyRule.org_id == flight.org_id, AgricultureAgronomyRule.status == "approved").order_by(AgricultureAgronomyRule.created_at.asc()))).all())
        evidence: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        for row in [*observations, *risks]:
            issue_type = getattr(row, "observation_type", None) or getattr(row, "issue_type", "unknown")
            item = {"source_id": row.id, "source_type": "confirmed_observation" if isinstance(row, AgricultureObservation) else "confirmed_crop_risk", "issue_type": issue_type, "crop_type": getattr(row, "crop_type", None), "severity": float(row.severity), "confidence": float(row.confidence), "trend": row.trend, "area_m2": row.area_m2, "uncertainty": redact_audit_value(row.uncertainty or {}), "model_version": getattr(row, "model_version", None)}
            evidence.append(item)
            citations.append(_citation(row.id, item["source_type"], row.created_at, ["issue_type", "severity", "confidence", "trend", "uncertainty"]))
        previous_flight = await db.scalar(select(AgricultureFlight).where(AgricultureFlight.field_id == flight.field_id, AgricultureFlight.id != flight.id).order_by(AgricultureFlight.created_at.desc()).limit(1))
        comparison_evidence: list[dict[str, Any]] = []
        if previous_flight is not None:
            previous_run = await db.scalar(select(AgricultureAnalysisRun).where(AgricultureAnalysisRun.flight_id == previous_flight.id).order_by(AgricultureAnalysisRun.created_at.desc()).limit(1))
            if previous_run is not None:
                previous_rows = list((await db.scalars(select(AgricultureObservation).where(AgricultureObservation.run_id == previous_run.id, AgricultureObservation.review_state == "confirmed"))).all())
                previous_rows += list((await db.scalars(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == previous_run.id, AgricultureCropRisk.review_state == "confirmed"))).all())
                for row in previous_rows:
                    item = {"source_id": row.id, "source_type": "reference_confirmed_observation", "issue_type": getattr(row, "observation_type", None) or getattr(row, "issue_type", "unknown"), "crop_type": getattr(row, "crop_type", None), "severity": float(row.severity), "confidence": float(row.confidence), "trend": row.trend, "area_m2": row.area_m2, "uncertainty": redact_audit_value(row.uncertainty or {}), "model_version": getattr(row, "model_version", None), "reference_flight_id": previous_flight.id}
                    comparison_evidence.append(item)
                    citations.append(_citation(row.id, item["source_type"], row.created_at, ["issue_type", "severity", "confidence", "trend", "uncertainty"]))
        fusion = list((await db.scalars(select(AgricultureFusionResult).where(AgricultureFusionResult.run_id == run.id))).all())
        layers = [{"source_id": row.id, "layer": row.layer_name, "status": row.status, "measured": row.measured, "summary": redact_audit_value(row.summary or {}), "confidence": row.confidence, "uncertainty": redact_audit_value(row.uncertainty or {})} for row in fusion if row.measured]
        stage = await db.scalar(select(AgricultureGrowthStageEstimate).where(AgricultureGrowthStageEstimate.run_id == run.id))
        metrics = list((await db.scalars(select(AgricultureGrowthMetric).where(AgricultureGrowthMetric.run_id == run.id, AgricultureGrowthMetric.status != "not_measured"))).all())
        rule_values = [{"id": row.id, "rule_key": row.rule_key, "version": row.version, "jurisdiction": row.jurisdiction, "crop_type": row.crop_type, "issue_type": row.issue_type, "action_kind": row.action_kind, "parameters": redact_audit_value(row.parameters or {}), "regulatory_reference": row.regulatory_reference} for row in rules]
        deterministic = evaluate_deterministic_rules(evidence, rule_values)
        context = {"context_version": "agriculture_context_v1", "field": {"field_id": flight.field_id, "crop_type": profile.crop_type if profile else flight.profile_snapshot.get("crop_type"), "variety": profile.variety if profile else flight.profile_snapshot.get("variety"), "season": profile.season if profile else flight.season, "growth_stage": (stage.human_stage or stage.predicted_stage) if stage else (profile.growth_stage if profile else None)}, "quality_gate": run.quality_gate or {}, "validated_observations": evidence, "comparison_reference": {"flight_id": previous_flight.id if previous_flight else None, "validated_observations": comparison_evidence}, "measured_layers": layers, "growth_metrics": [{"metric_kind": row.metric_kind, "status": row.status, "summary": redact_audit_value(row.summary or {}), "confidence": row.confidence, "uncertainty": redact_audit_value(row.uncertainty or {})} for row in metrics], "growth_stage": {"stage": (stage.human_stage or stage.predicted_stage), "confidence": stage.confidence, "evidence_ids": stage.evidence_ids, "uncertainty": redact_audit_value(stage.uncertainty or {})} if stage else None, "approved_rules": rule_values, "deterministic_findings": deterministic, "citations": citations, "limitations": ["Only confirmed evidence is included.", "Raw frames, media notes, secrets and unvalidated measurements are excluded.", "Treatment, chemical and fertilizer decisions require agronomist approval."]}
        context["context_checksum"] = _checksum(context)
        context["source_ids"] = [item["source_id"] for item in evidence] + [item["source_id"] for item in comparison_evidence] + [item["source_id"] for item in layers]
        return context

    @staticmethod
    def _fallback(task: str, context: dict[str, Any], error_code: str, *, question_blocked: bool = False) -> AgricultureAssistantResponse:
        findings = context.get("deterministic_findings", [])
        source_ids = [str(item["source_id"]) for item in findings]
        summary = "No new agronomic claim was generated. Review confirmed evidence and deterministic findings." if findings else "No confirmed agriculture evidence is available for a grounded assistant answer."
        if question_blocked:
            summary = "The request was refused because it contained instruction-like text. Ask a plain field-data question."
        return AgricultureAssistantResponse(summary=summary, key_points=[f"{len(context.get('validated_observations', []))} confirmed evidence item(s)", f"{len(findings)} deterministic rule finding(s)"], next_steps=["Review the cited evidence.", "Have an agronomist approve any disease, pest, nutrient or treatment conclusion."], cited_source_ids=source_ids, risk_level="high" if findings else "medium", confidence=0.0, human_approval_required=True, abstained=True, decision_status="provider_unavailable" if not question_blocked else "model_uncertain", limitations=context.get("limitations", []) + [f"Assistant fallback: {error_code}." ])

    async def run(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, task: str, question: str, user_id: int | None, org_id: int | None) -> AgricultureAssistantRun:
        context = await self.build_context(db, run=run, flight=flight)
        try:
            clean_question = sanitize_question(question)
        except PromptInjectionBlocked as exc:
            clean_question = "[blocked instruction-like input]"
            error_code = PromptInjectionBlocked.code
            output = self._fallback(task, context, error_code, question_blocked=True)
            profile_id = model = None
            status = "blocked"
        else:
            error_code = None
            profile_id = model = None
            status = "ok"
            try:
                prompt = f"{GOVERNANCE_PROMPT}\nUse only the JSON context. Cite only source_id values present in citations. If evidence is insufficient, abstain. Always require human approval. Return exactly the requested JSON schema."
                response_profile, response = await chat_with_task("field_survey", [LLMMessage(role="system", content=prompt), LLMMessage(role="user", content=json.dumps({"task": task, "question": clean_question, "context": context}, sort_keys=True, default=str))], response_model=AgricultureAssistantResponse, temperature=0.1, max_tokens=1800, retry_budget=1, deadline_seconds=30)
                profile_id = response_profile.id
                model = response.model or response_profile.model
                raw = response.content.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
                output = AgricultureAssistantResponse.model_validate(json.loads(raw))
                if any(_UNSAFE_RECOMMENDATION_RE.search(text) for text in [output.summary, *output.key_points, *output.next_steps]):
                    raise ValueError("unsafe_recommendation_content")
                allowed = set(context["source_ids"])
                if not set(output.cited_source_ids).issubset(allowed):
                    raise ValueError("ungrounded_source_citation")
                output.human_approval_required = True
            except Exception as exc:
                error_code = "provider_or_schema_error" if not isinstance(exc, ValueError) else str(exc)[:128]
                output = self._fallback(task, context, error_code)
                status = "fallback"
        row = AgricultureAssistantRun(org_id=org_id, field_id=flight.field_id, flight_id=flight.id, run_id=run.id, task=task, status=status, decision_status=output.decision_status, prompt_version=PROMPT_VERSION, prompt_hash=_checksum("agriculture-governance-prompt-v1"), context_checksum=context["context_checksum"], question_redacted=clean_question[:4000], source_ids=context["source_ids"], deterministic_rules=context["deterministic_findings"], output=output.model_dump(mode="json"), citations=[citation for citation in context["citations"] if citation["source_id"] in output.cited_source_ids], limitations=output.limitations, confidence=output.confidence, risk_level=output.risk_level, requires_human_approval=True, abstained=output.abstained, profile_id=profile_id, model=model, error_code=error_code)
        db.add(row)
        db.add(AgricultureGovernanceAudit(org_id=org_id, entity_type="assistant_run", entity_id=row.id, actor_user_id=user_id, action="created", to_status=status, reason=error_code, payload={"context_checksum": context["context_checksum"], "source_count": len(context["source_ids"]), "prompt_version": PROMPT_VERSION}))
        await db.commit()
        await db.refresh(row)
        return row

    async def review(self, db: AsyncSession, *, row: AgricultureAssistantRun, status: str, note: str | None, user_id: int | None, org_id: int | None) -> AgricultureAssistantRun:
        previous = row.review_status
        row.review_status = status
        row.reviewed_by_user_id = user_id
        row.review_note = note
        row.reviewed_at = datetime.now(UTC)
        db.add(AgricultureGovernanceAudit(org_id=org_id, entity_type="assistant_run", entity_id=row.id, actor_user_id=user_id, action="review", from_status=previous, to_status=status, reason=note, payload={"requires_human_approval": row.requires_human_approval}))
        await db.commit()
        await db.refresh(row)
        return row


agriculture_governance_service = AgricultureGovernanceService()
