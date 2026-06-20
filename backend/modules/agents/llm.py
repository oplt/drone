from __future__ import annotations

import logging
from typing import Any

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.infrastructure.ai.base import LLMChatRequest, LLMMessage
from backend.infrastructure.ai.errors import LLMNetworkError
from backend.infrastructure.ai.local_llm_runtime import chat_with_profile
from backend.modules.ai.schemas import LLMTaskName
from backend.modules.ai.service import AISettingsService

logger = logging.getLogger(__name__)


async def chat_with_task(
    task: LLMTaskName,
    messages: list[LLMMessage],
    *,
    extra_system: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> tuple[Any, Any]:
    """Resolve profile for *task* and run a chat completion."""
    service = AISettingsService()
    profile = await service.resolve_profile_for_task(task)
    if profile is None:
        raise RuntimeError(f"No enabled LLM profile for task '{task}'")

    settings = await service.get_settings(effective=True)
    system_parts = [settings.system_prompt.strip()]
    if extra_system.strip():
        system_parts.append(extra_system.strip())
    merged_system = "\n\n".join(part for part in system_parts if part)

    request_messages = list(messages)
    if merged_system:
        if request_messages and request_messages[0].role == "system":
            request_messages[0] = LLMMessage(
                role="system",
                content=f"{merged_system}\n\n{request_messages[0].content}",
            )
        else:
            request_messages.insert(0, LLMMessage(role="system", content=merged_system))

    request = LLMChatRequest(
        messages=request_messages,
        model=profile.model,
        temperature=temperature if temperature is not None else profile.temperature,
        max_tokens=max_tokens if max_tokens is not None else profile.max_tokens,
        stream=False,
    )
    response = None
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(LLMNetworkError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            response = await chat_with_profile(profile, request)
    if response is None:
        raise RuntimeError("LLM chat completed without a response")
    return profile, response
