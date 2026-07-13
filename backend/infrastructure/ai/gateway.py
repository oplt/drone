"""Reusable, policy-aware gateway for mission LLM calls."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.infrastructure.ai.base import LLMChatRequest, LLMChatResponse, LLMMessage
from backend.infrastructure.ai.errors import (
    LLMConfigError,
    LLMProviderUnavailableError,
    LLMUnsupportedModelError,
)
from backend.infrastructure.ai.factory import create_llm_client
from backend.infrastructure.ai.http import shared_http_sessions
from backend.infrastructure.ai.local_llm_runtime import (
    _client_config_from_profile,
    ensure_profile_ready,
)
from backend.infrastructure.cache.local import BoundedTTLCache
from backend.modules.ai.schemas import LLMProfile, LLMTaskName
from backend.modules.ai.service import AISettingsService
from backend.observability import prometheus_metrics
from backend.observability.instruments import observed_span

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class _Circuit:
    failures: int = 0
    open_until: float = 0.0


def _parse_json(content: str) -> dict[str, Any]:
    if len(content.encode("utf-8")) > 128_000:
        raise ValueError("Structured AI response exceeds 128 KiB")
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Structured AI response must be a JSON object")
    return value


def _usage_tokens(response: LLMChatResponse) -> dict[str, int]:
    usage = response.raw.get("usage") if isinstance(response.raw, dict) else None
    if not isinstance(usage, dict):
        return {}
    aliases = {
        "prompt": ("prompt_tokens", "input_tokens"),
        "completion": ("completion_tokens", "output_tokens"),
        "total": ("total_tokens",),
    }
    result: dict[str, int] = {}
    for kind, names in aliases.items():
        for name in names:
            try:
                value = int(usage.get(name))
            except (TypeError, ValueError):
                continue
            if value >= 0:
                result[kind] = value
                break
    return result


def _retryable(error: BaseException) -> bool:
    """Only transient transport/time-limit errors get another same-provider try."""
    if isinstance(error, (ValidationError, ValueError, LLMConfigError, LLMUnsupportedModelError)):
        return False
    if isinstance(error, LLMProviderUnavailableError):
        return False
    return isinstance(error, (TimeoutError, asyncio.TimeoutError, OSError, RuntimeError))


class AIGateway:
    """Pool clients, cache routing, enforce budgets, and fail over safely."""

    def __init__(
        self,
        settings_service: AISettingsService | None = None,
        *,
        session_registry: Any | None = None,
    ) -> None:
        self.settings_service = settings_service or AISettingsService()
        self.session_registry = session_registry or shared_http_sessions
        self._task_profiles = BoundedTTLCache[tuple[int, list[LLMProfile]]](max_entries=64)
        self._clients = BoundedTTLCache[Any](max_entries=64)
        self._profile_lock = asyncio.Lock()
        self._client_lock = asyncio.Lock()
        self._circuits: dict[str, _Circuit] = {}

    async def _profiles_for_task(self, task: LLMTaskName) -> list[LLMProfile]:
        if hasattr(self.settings_service, "shared_cache_revision"):
            revision = await self.settings_service.shared_cache_revision()
        else:
            revision = self.settings_service.cache_revision()
        cached = self._task_profiles.get(task, ttl_seconds=30.0)
        if cached and cached[0] == revision:
            return cached[1]

        settings = await self.settings_service.get_settings(effective=True)
        primary = await self.settings_service.resolve_profile_for_task(task)
        if primary is None:
            raise RuntimeError(f"No enabled LLM profile for task '{task}'")
        profiles = [primary]
        # Fallback stays within the same privacy class; never silently send local data to cloud.
        profiles.extend(
            profile
            for profile in settings.profiles
            if profile.enabled
            and profile.id != primary.id
            and profile.privacy_mode == primary.privacy_mode
        )
        async with self._profile_lock:
            self._task_profiles.set(task, (revision, profiles))
        return profiles

    async def _client_for(self, profile: LLMProfile) -> Any:
        client_key = ":".join(
            (
                profile.id,
                profile.updated_at or "",
                profile.provider,
                profile.api_base,
                profile.model,
            )
        )
        client = self._clients.get(client_key)
        if client is not None:
            return client
        async with self._client_lock:
            client = self._clients.get(client_key)
            if client is None:
                config = _client_config_from_profile(profile)
                try:
                    client = create_llm_client(
                        config,
                        session_registry=self.session_registry,
                    )
                except TypeError as exc:
                    # Keep compatibility with lightweight injected factories in tests/tools.
                    if "session_registry" not in str(exc):
                        raise
                    client = create_llm_client(config)
                self._clients.set(client_key, client)
            return client

    @staticmethod
    def _response_format(
        profile: LLMProfile,
        response_model: type[T] | None,
    ) -> dict[str, Any] | None:
        if response_model is None:
            return None
        schema = response_model.model_json_schema()
        if profile.provider == "ollama":
            return schema
        if profile.provider in {"openai", "openai_compatible", "huggingface", "llama_cpp"}:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__.lower(),
                    "strict": True,
                    "schema": schema,
                },
            }
        return {"type": "json_object"}

    @staticmethod
    def _with_system_message(messages: list[LLMMessage], extra_system: str) -> list[LLMMessage]:
        if not extra_system.strip():
            return list(messages)
        result = list(messages)
        if result and result[0].role == "system":
            result[0] = LLMMessage(
                role="system",
                content=f"{extra_system.strip()}\n\n{result[0].content}",
            )
        else:
            result.insert(0, LLMMessage(role="system", content=extra_system.strip()))
        return result

    def _circuit_allows(self, profile: LLMProfile) -> bool:
        circuit = self._circuits.setdefault(profile.id, _Circuit())
        return circuit.open_until <= time.monotonic()

    def _record_success(self, profile: LLMProfile) -> None:
        self._circuits[profile.id] = _Circuit()

    def _record_failure(self, profile: LLMProfile) -> None:
        circuit = self._circuits.setdefault(profile.id, _Circuit())
        circuit.failures += 1
        if circuit.failures >= 3:
            circuit.open_until = time.monotonic() + 30.0

    async def complete_task(
        self,
        task: LLMTaskName,
        messages: list[LLMMessage],
        *,
        extra_system: str = "",
        temperature: float | None = None,
        token_budget: int | None = None,
        response_model: type[T] | None = None,
        retry_budget: int = 1,
        deadline_seconds: float | None = None,
    ) -> tuple[LLMProfile, LLMChatResponse, T | None]:
        profiles = await self._profiles_for_task(task)
        last_error: Exception | None = None
        overall_deadline = time.monotonic() + max(
            0.01,
            float(
                deadline_seconds
                if deadline_seconds is not None
                else profiles[0].timeout_seconds
            ),
        )
        for index, profile in enumerate(profiles):
            if time.monotonic() >= overall_deadline:
                break
            if not self._circuit_allows(profile):
                continue
            attempts = max(1, min(3, int(retry_budget) + 1))
            budget = min(profile.max_tokens, token_budget or profile.max_tokens)
            request = LLMChatRequest(
                messages=self._with_system_message(messages, extra_system),
                model=profile.model,
                temperature=temperature if temperature is not None else profile.temperature,
                max_tokens=budget,
                stream=False,
                response_format=self._response_format(profile, response_model),
            )
            for attempt in range(attempts):
                started = time.perf_counter()
                try:
                    remaining = overall_deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("AI request deadline exceeded")
                    await ensure_profile_ready(profile)
                    client = await self._client_for(profile)
                    with observed_span(
                        "ai.request",
                        task=task,
                        provider=profile.provider,
                        model=profile.model,
                    ) as span:
                        response = await asyncio.wait_for(
                            client.chat(request),
                            timeout=min(float(profile.timeout_seconds), remaining),
                        )
                        if span is not None:
                            span.set_attribute("ai.token_budget", budget)
                    parsed = (
                        response_model.model_validate(_parse_json(response.content))
                        if response_model
                        else None
                    )
                    for kind, value in _usage_tokens(response).items():
                        prometheus_metrics.ai_tokens_total.labels(
                            task=task, provider=profile.provider, kind=kind
                        ).inc(value)
                    self._record_success(profile)
                    prometheus_metrics.ai_requests_total.labels(
                        task=task, provider=profile.provider, status="success"
                    ).inc()
                    if index:
                        prometheus_metrics.ai_fallback_total.labels(task=task).inc()
                    return profile, response, parsed
                except Exception as exc:
                    last_error = exc
                    prometheus_metrics.ai_requests_total.labels(
                        task=task, provider=profile.provider, status="error"
                    ).inc()
                    if (
                        attempt + 1 < attempts
                        and _retryable(exc)
                        and time.monotonic() < overall_deadline
                    ):
                        prometheus_metrics.retry_count_total.labels(
                            subsystem="ai_gateway", reason="provider_retry"
                        ).inc()
                        delay = min(0.25 * (2**attempt), 1.0)
                        await asyncio.sleep(delay * random.uniform(0.8, 1.2))
                    else:
                        self._record_failure(profile)
                        logger.warning(
                            "AI provider failed task=%s profile=%s attempts=%s",
                            task,
                            profile.id,
                            attempts,
                        )
                finally:
                    prometheus_metrics.ai_request_duration_seconds.labels(task=task).observe(
                        time.perf_counter() - started
                    )
        raise RuntimeError("All configured AI providers failed") from last_error

    async def close(self) -> None:
        self._clients.clear()
        self._task_profiles.clear()
        await self.session_registry.close()


ai_gateway = AIGateway()
