from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agents.models import AgentRun
from backend.modules.agents.schemas import AgentRunOut, AgentResult

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt_template(relative_path: str) -> str:
    path = _PROMPTS_DIR / relative_path
    return path.read_text(encoding="utf-8").strip()


def render_prompt(template: str, context: dict[str, object]) -> str:
    payload = json.dumps(context, indent=2, sort_keys=True, default=str)
    if "{context_json}" in template:
        return template.replace("{context_json}", payload)
    return f"{template}\n\n## Mission context\n\n```json\n{payload}\n```"


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_structured_response(content: str) -> tuple[str, dict[str, object] | None]:
    stripped = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", stripped)
    if fence:
        try:
            structured = json.loads(fence.group(1))
            if isinstance(structured, dict):
                summary = str(
                    structured.get("operator_message")
                    or structured.get("incident_summary")
                    or structured.get("coverage_summary")
                    or structured.get("field_summary")
                    or structured.get("route_summary")
                    or structured.get("inspection_summary")
                    or structured.get("summary")
                    or stripped
                )
                return summary, structured
        except json.JSONDecodeError:
            pass
    if stripped.startswith("{"):
        try:
            structured = json.loads(stripped)
            if isinstance(structured, dict):
                summary = str(
                    structured.get("operator_message")
                    or structured.get("summary")
                    or stripped
                )
                return summary, structured
        except json.JSONDecodeError:
            pass
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
            structured_result=result.structured,
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
