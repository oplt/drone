from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.infrastructure.ai.base import LLMMessage
from backend.infrastructure.ai.gateway import ai_gateway
from backend.modules.ai.schemas import LLMTaskName


async def close_ai_gateway() -> None:
    await ai_gateway.close()


async def chat_with_task(
    task: LLMTaskName,
    messages: list[LLMMessage],
    *,
    extra_system: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_model: type[BaseModel] | None = None,
    retry_budget: int = 1,
    deadline_seconds: float | None = None,
) -> tuple[Any, Any]:
    """Resolve profile for *task* and run a chat completion."""
    service = ai_gateway.settings_service
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

    resolved_profile, response, _ = await ai_gateway.complete_task(
        task,
        request_messages,
        temperature=temperature,
        token_budget=max_tokens,
        response_model=response_model,
        retry_budget=retry_budget,
        deadline_seconds=deadline_seconds,
    )
    return resolved_profile, response
