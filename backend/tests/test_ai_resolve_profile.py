from __future__ import annotations

from backend.modules.ai.service import AISettingsService
from backend.modules.ai.schemas import LLMProfile


def test_resolve_profile_for_task_uses_override(monkeypatch) -> None:
    import asyncio

    service = AISettingsService()
    profile = LLMProfile(
        id="warehouse-planner",
        name="Warehouse Planner",
        provider="ollama",
        api_base="http://localhost:11434",
        model="llama3",
        enabled=True,
        privacy_mode="local",
        has_api_key=False,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    async def fake_settings(*, effective: bool = False):
        from backend.modules.ai.schemas import LLMSettingsResponse

        return LLMSettingsResponse.model_validate(
            {
                "active_provider": "ollama",
                "system_prompt": "test",
                "providers": {},
                "task_defaults": {},
                "profiles": [profile.model_dump()],
                "default_profile_id": "",
                "task_overrides": {"mission_planning": "warehouse-planner"},
            }
        )

    monkeypatch.setattr(service, "get_settings", fake_settings)
    resolved = asyncio.run(service.resolve_profile_for_task("mission_planning"))
    assert resolved is not None
    assert resolved.id == "warehouse-planner"


def test_resolve_profile_for_task_returns_none_when_disabled(monkeypatch) -> None:
    import asyncio

    service = AISettingsService()

    async def fake_settings(*, effective: bool = False):
        from backend.modules.ai.schemas import LLMSettingsResponse

        return LLMSettingsResponse.model_validate(
            {
                "active_provider": "ollama",
                "system_prompt": "test",
                "providers": {},
                "task_defaults": {},
                "profiles": [],
                "default_profile_id": "",
                "task_overrides": {},
            }
        )

    monkeypatch.setattr(service, "get_settings", fake_settings)
    assert asyncio.run(service.resolve_profile_for_task("mission_planning")) is None
