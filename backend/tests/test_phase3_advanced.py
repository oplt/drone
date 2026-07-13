from __future__ import annotations

from typing import ClassVar

import pytest


def _profile(profile_id: str, *, privacy_mode: str = "local"):
    from backend.modules.ai.schemas import LLMProfile

    return LLMProfile(
        id=profile_id,
        name=profile_id,
        provider="ollama",
        model="test-model",
        privacy_mode=privacy_mode,
    )


@pytest.mark.asyncio
async def test_ai_gateway_uses_same_privacy_fallback_and_structured_output(monkeypatch) -> None:
    from backend.infrastructure.ai import gateway
    from backend.infrastructure.ai.base import LLMChatResponse
    from backend.infrastructure.ai.gateway import AIGateway
    from backend.modules.ai.schemas import LLMTaskName

    primary = _profile("primary")
    fallback = _profile("fallback")

    class Settings:
        profiles: ClassVar[list] = [primary, fallback]

    class Service:
        async def get_settings(self, *, effective):
            return Settings()

        async def resolve_profile_for_task(self, task: LLMTaskName):
            return primary

    class Client:
        def __init__(self, profile_id):
            self.profile_id = profile_id

        async def chat(self, _request):
            if self.profile_id == "primary":
                raise RuntimeError("primary unavailable")
            return LLMChatResponse(
                provider="ollama",
                model="test-model",
                content='{"operator_message":"ok","confidence":0.9}',
            )

    monkeypatch.setattr(gateway, "ensure_profile_ready", lambda _profile: _done())
    monkeypatch.setattr(
        gateway,
        "create_llm_client",
        lambda config: Client(
            config.model if config.model in {"primary", "fallback"} else "fallback"
        ),
    )
    # Use profile id as the model only for the deterministic fake client.
    primary.model = "primary"
    fallback.model = "fallback"
    response = await AIGateway(Service()).complete_task("assistant", [])

    assert response[0].id == "fallback"
    assert response[2] is None


async def _done() -> None:
    return None


def test_ai_evaluation_redacts_secrets_and_enforces_approval() -> None:
    from backend.modules.ai.evaluation import EvaluationCase, evaluate_case

    result = evaluate_case(
        EvaluationCase(
            case_id="approval-1",
            prompt_version="v2",
            input={},
            expected={"operator_message": "review"},
            requires_human_approval=True,
        ),
        {
            "operator_message": "review",
            "api_key": "secret",
            "confidence": 0.4,
            "requires_human_approval": True,
        },
    )

    assert result.passed is True
    assert result.abstained is True
    assert result.redacted_output["api_key"] == "[REDACTED]"


def test_versioned_retrieval_filters_metadata_and_returns_citations() -> None:
    from backend.infrastructure.ai.retrieval import chunk_document, retrieve

    chunks = chunk_document(
        "Battery low. Return to dock immediately. " * 10,
        source="mission-manual.md",
        version="v3",
        metadata={"org_id": 7},
    )
    hits = retrieve("battery low", chunks, metadata_filter={"org_id": 7}, limit=1)

    assert hits
    assert hits[0].chunk.version == "v3"
    assert hits[0].citation.startswith("[mission-manual.md#")
    assert retrieve("battery low", chunks, metadata_filter={"org_id": 8}) == []


@pytest.mark.asyncio
async def test_read_model_projector_writes_tenant_scoped_keys(monkeypatch) -> None:
    from backend.modules.read_models.projector import ReadModelProjector

    writes: list[tuple[str, str, int]] = []

    class Redis:
        async def set(self, key, value, ex):
            writes.append((key, value, ex))

    monkeypatch.setattr(
        "backend.modules.read_models.projector.get_redis_client", lambda: Redis()
    )
    await ReadModelProjector().project_alert(org_id=7, alert_id=2, payload={"status": "open"})

    assert writes[0][0] == "read-model:alert:7:2"
