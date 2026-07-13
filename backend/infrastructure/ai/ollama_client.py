from __future__ import annotations

import aiohttp

from backend.infrastructure.ai.base import (
    BaseLLMClient,
    LLMChatRequest,
    LLMChatResponse,
    LLMHealth,
    LLMModel,
)
from backend.infrastructure.ai.errors import (
    LLMConfigError,
    LLMNetworkError,
    LLMProviderUnavailableError,
)


class OllamaClient(BaseLLMClient):
    async def health_check(self) -> LLMHealth:
        try:
            models = await self.list_models()
        except Exception as exc:
            return LLMHealth(
                ok=False,
                status="unreachable",
                detail=str(exc),
                provider=self.config.provider,
            )
        return LLMHealth(
            ok=True,
            status="running",
            detail="Ollama reachable." if models else "Ollama reachable; no models found.",
            provider=self.config.provider,
            model_count=len(models),
        )

    async def list_models(self) -> list[LLMModel]:
        url = f"{self.config.api_base.rstrip('/')}/api/tags"
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        session = await self._session()
        try:
            async with session.get(url, timeout=timeout) as response:
                if response.status >= 400:
                    raise LLMProviderUnavailableError(
                        f"Ollama model discovery failed with HTTP {response.status}."
                    )
                data = await response.json()
        except LLMProviderUnavailableError:
            raise
        except Exception as exc:
            raise LLMNetworkError("Ollama is unreachable.", detail=str(exc)) from exc
        raw_models = data.get("models") if isinstance(data, dict) else []
        return [
            LLMModel(id=str(item.get("name")), name=str(item.get("name")), local=True)
            for item in raw_models
            if isinstance(item, dict) and item.get("name")
        ]

    async def chat(self, request: LLMChatRequest) -> LLMChatResponse:
        model = request.model or self.config.model
        if not model:
            raise LLMConfigError("Model is required.")
        payload = {
            "model": model,
            "stream": False,
            "messages": [message.model_dump() for message in request.messages],
            "options": {
                "temperature": (
                    request.temperature
                    if request.temperature is not None
                    else self.config.temperature
                ),
                "num_predict": (
                    request.max_tokens
                    if request.max_tokens is not None
                    else self.config.max_tokens
                ),
            },
        }
        if request.response_format:
            payload["format"] = request.response_format
        url = f"{self.config.api_base.rstrip('/')}/api/chat"
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        session = await self._session()
        try:
            async with session.post(url, json=payload, timeout=timeout) as response:
                if response.status == 404:
                    raise LLMProviderUnavailableError("Ollama model not found.")
                if response.status >= 400:
                    text = await response.text()
                    raise LLMProviderUnavailableError(
                        f"Ollama chat failed with HTTP {response.status}.",
                        detail=text[:300],
                    )
                data = await response.json()
        except LLMProviderUnavailableError:
            raise
        except Exception as exc:
            raise LLMNetworkError("Ollama chat network failure.", detail=str(exc)) from exc
        message = data.get("message") if isinstance(data, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        return LLMChatResponse(
            provider=self.config.provider,
            model=model,
            content=str(content or ""),
            raw=data,
        )
