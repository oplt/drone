from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.infrastructure.ai.base import LLMChatResponse
from backend.modules.agents.output_validation import validate_agent_output
from backend.modules.agents.registry import get
from backend.modules.agents.schemas import (
    AgentContext,
    AgentOutputType,
    AgentPhase,
    MissionAgentId,
)
from backend.modules.agents.service import MissionAgentService, agent_enabled
from backend.modules.ai.schemas import LLMProfile


@pytest.mark.parametrize(
    "agent_id",
    [
        MissionAgentId.PRIVATE_PATROL,
        MissionAgentId.WAREHOUSE_SCAN,
        MissionAgentId.FIELD_SURVEY,
    ],
)
def test_agent_registry_contains_phase1_to_phase3_agents(agent_id: MissionAgentId) -> None:
    definition = get(agent_id)
    assert definition.llm_task
    assert definition.prompt_template_path.endswith(".md")


def test_agent_enabled_respects_settings_flags() -> None:
    assert not agent_enabled(
        MissionAgentId.WAREHOUSE_SCAN,
        {"enabled": True, "warehouse_scan": False},
    )
    assert not agent_enabled(
        MissionAgentId.WAREHOUSE_SCAN,
        {"enabled": False, "warehouse_scan": True},
    )


def test_mission_agent_service_parses_json_response(monkeypatch) -> None:
    profile = LLMProfile(
        id="local",
        name="Local",
        provider="ollama",
        api_base="http://localhost:11434",
        model="llama3",
        enabled=True,
    )
    response = LLMChatResponse(
        provider="ollama",
        model="llama3",
        content=(
            '{"operator_message":"Scan looks partial.","scan_quality":"partial",'
            '"risk_level":"medium","recommended_next_scan":["Repeat aisle 4"]}'
        ),
    )

    async def _fake_chat_with_task(*_args, **_kwargs):
        return profile, response

    monkeypatch.setattr(
        "backend.modules.agents.service.chat_with_task",
        _fake_chat_with_task,
    )
    monkeypatch.setattr(
        MissionAgentService,
        "_agents_doc",
        AsyncMock(return_value={"enabled": True, "warehouse_scan": True}),
    )

    service = MissionAgentService(settings_repo=AsyncMock())
    context = AgentContext(
        phase=AgentPhase.ON_DEMAND,
        mission_type="warehouse_scan",
        question="How is scan quality?",
        structured_payload={"warehouse_map_id": 1},
    )
    result = asyncio.run(
        service.run(MissionAgentId.WAREHOUSE_SCAN, context, db=None, persist=False)
    )
    assert result.status == "ok"
    assert "partial" in result.text.lower()
    assert result.structured is not None
    assert result.structured.get("scan_quality") == "partial"
    assert result.risk_level == "medium"


@pytest.mark.parametrize(
    "content, expected_error",
    [
        ("Scan looks good.", "JSON object"),
        ('{"risk_level":"low"}', "operator_message"),
    ],
)
def test_mission_agent_service_rejects_invalid_output(
    monkeypatch,
    content: str,
    expected_error: str,
) -> None:
    profile = LLMProfile(
        id="local",
        name="Local",
        provider="ollama",
        api_base="http://localhost:11434",
        model="llama3",
        enabled=True,
    )
    response = LLMChatResponse(
        provider="ollama",
        model="llama3",
        content=content,
    )

    async def _fake_chat_with_task(*_args, **_kwargs):
        return profile, response

    monkeypatch.setattr(
        "backend.modules.agents.service.chat_with_task",
        _fake_chat_with_task,
    )
    monkeypatch.setattr(
        MissionAgentService,
        "_agents_doc",
        AsyncMock(return_value={"enabled": True, "warehouse_scan": True}),
    )

    result = asyncio.run(
        MissionAgentService(settings_repo=AsyncMock()).run(
            MissionAgentId.WAREHOUSE_SCAN,
            AgentContext(
                phase=AgentPhase.ON_DEMAND,
                mission_type="warehouse_scan",
            ),
            persist=False,
        )
    )

    assert result.status == "error"
    assert expected_error in (result.error_message or "")


def test_mission_draft_always_requires_human_approval() -> None:
    validated = validate_agent_output(
        AgentOutputType.MISSION_DRAFT,
        {
            "operator_message": "Draft ready.",
            "requires_human_approval": False,
        },
    )

    assert validated.requires_human_approval is True


def test_mission_agent_service_enforces_phase_timeout(monkeypatch) -> None:
    definition = get(MissionAgentId.WAREHOUSE_SCAN).model_copy(update={"timeout_seconds": 0})

    async def _slow_chat_with_task(*_args, **_kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(
        "backend.modules.agents.service.chat_with_task",
        _slow_chat_with_task,
    )
    monkeypatch.setattr("backend.modules.agents.service.get", lambda _agent_id: definition)
    monkeypatch.setattr(
        MissionAgentService,
        "_agents_doc",
        AsyncMock(return_value={"enabled": True, "warehouse_scan": True}),
    )

    result = asyncio.run(
        MissionAgentService(settings_repo=AsyncMock()).run(
            MissionAgentId.WAREHOUSE_SCAN,
            AgentContext(
                phase=AgentPhase.ON_DEMAND,
                mission_type="warehouse_scan",
            ),
            persist=False,
        )
    )

    assert result.status == "error"
    assert result.error_message == "Agent exceeded 0s timeout"
