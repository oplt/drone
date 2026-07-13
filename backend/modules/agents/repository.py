from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agents.models import AgentRun
from backend.modules.agents.schemas import AgentResult, AgentRunOut

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_REDACTED_KEYS = {"api_key", "token", "password", "secret", "authorization", "access_token"}
_UNTRUSTED_TEXT_KEYS = {
    "description",
    "external_text",
    "metadata",
    "notes",
    "operator_text",
    "raw",
    "results",
}
_MAX_PROMPT_DEPTH = 6
_MAX_PROMPT_STRING = 4000
_MAX_PROMPT_ITEMS = 64
_MAX_PROMPT_TOTAL = 32_000
_MAX_RESPONSE_BYTES = 128_000


def _sensitive_key(key: object) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _REDACTED_KEYS)


def _bounded_prompt_value(value: object, *, key: object = "", depth: int = 0) -> object:
    if _sensitive_key(key):
        return "[REDACTED]"
    if depth >= _MAX_PROMPT_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            str(item_key): _bounded_prompt_value(item, key=item_key, depth=depth + 1)
            for item_key, item in list(value.items())[:_MAX_PROMPT_ITEMS]
        }
    if isinstance(value, (list, tuple, set)):
        return [
            _bounded_prompt_value(item, depth=depth + 1)
            for item in list(value)[:_MAX_PROMPT_ITEMS]
        ]
    if isinstance(value, str):
        bounded = value[:_MAX_PROMPT_STRING]
        if str(key).lower() in _UNTRUSTED_TEXT_KEYS:
            return f"<untrusted_external_text>{bounded}</untrusted_external_text>"
        return bounded
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_PROMPT_STRING]


def redact_audit_value(value: object) -> object:
    """Remove credential-like fields before persisting AI audit material."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if _sensitive_key(key)
            else redact_audit_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_audit_value(item) for item in value]
    return value


def load_prompt_template(relative_path: str) -> str:
    path = _PROMPTS_DIR / relative_path
    return path.read_text(encoding="utf-8").strip()


def render_prompt(
    template: str,
    context: dict[str, object],
    *,
    allowed_fields: set[str] | frozenset[str] | None = None,
) -> str:
    if allowed_fields is not None:
        context = {
            key: value
            for key, value in context.items()
            if key in allowed_fields
        }
    payload = json.dumps(
        _bounded_prompt_value(context),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    )
    if len(payload) > _MAX_PROMPT_TOTAL:
        payload = payload[:_MAX_PROMPT_TOTAL] + "\n...[TRUNCATED]"
    if "{context_json}" in template:
        return template.replace("{context_json}", payload)
    return f"{template}\n\n## Mission context\n\n```json\n{payload}\n```"


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_structured_response(content: str) -> tuple[str, dict[str, object] | None]:
    if len(content.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise ValueError("AI response exceeds 128 KiB")
    stripped = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else stripped
    if candidate.startswith("{"):
        try:
            structured, end = json.JSONDecoder().raw_decode(candidate)
            if candidate[end:].strip() or not isinstance(structured, dict):
                raise ValueError("AI response must contain only one JSON object")
            summary = str(
                structured.get("operator_message")
                or structured.get("incident_summary")
                or structured.get("coverage_summary")
                or structured.get("field_summary")
                or structured.get("route_summary")
                or structured.get("inspection_summary")
                or structured.get("summary")
                or candidate
            )
            return summary, structured
        except json.JSONDecodeError as exc:
            raise ValueError("AI response contains invalid JSON") from exc
        except ValueError:
            raise
    return stripped, None


class AgentRunRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        result: AgentResult,
        llm_task: str,
        prompt_text: str,
        mission_runtime_id: int | None,
    ) -> AgentRun:
        row = AgentRun(
            mission_runtime_id=mission_runtime_id,
            agent_id=result.agent_id.value,
            phase=result.phase.value,
            llm_task=llm_task,
            profile_id=result.profile_id,
            model=result.model,
            prompt_version=result.prompt_version,
            prompt_hash=prompt_hash(prompt_text),
            response_preview=(result.text or "")[:500] or None,
            structured_result=redact_audit_value(result.structured),
            latency_ms=result.latency_ms,
            status=result.status,
            error_message=result.error_message,
        )
        db.add(row)
        await db.flush()
        return row

    async def list_for_mission(
        self,
        db: AsyncSession,
        *,
        mission_runtime_id: int,
        limit: int = 20,
    ) -> list[AgentRun]:
        result = await db.execute(
            select(AgentRun)
            .where(AgentRun.mission_runtime_id == mission_runtime_id)
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    def to_out(row: AgentRun) -> AgentRunOut:
        created = row.created_at
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return AgentRunOut(
            id=row.id,
            agent_id=row.agent_id,
            phase=row.phase,
            llm_task=row.llm_task,
            profile_id=row.profile_id,
            model=row.model,
            prompt_version=row.prompt_version,
            response_preview=row.response_preview,
            structured_result=row.structured_result,
            latency_ms=row.latency_ms,
            status=row.status,
            error_message=row.error_message,
            mission_runtime_id=row.mission_runtime_id,
            created_at=created.isoformat() if created else None,
        )
