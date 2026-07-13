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


class OpenAICompatibleClient(BaseLLMClient):
    async def health_check(self) -> LLMHealth:
        if not self.config.api_base:
            return LLMHealth(
                ok=False,
                status="not_configured",
                detail="API base URL is required.",
                provider=self.config.provider,
            )
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
            detail="Provider reachable.",
            provider=self.config.provider,
            model_count=len(models),
        )

    async def list_models(self) -> list[LLMModel]:
        url = f"{self.config.api_base.rstrip('/')}/models"
        headers = self._headers()
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        session = await self._session()
        try:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status in {401, 403}:
                    raise LLMProviderUnavailableError("Invalid API key or unauthorized.")
                if response.status >= 400:
                    raise LLMProviderUnavailableError(
                        f"Model discovery failed with HTTP {response.status}."
                    )
                data = await response.json()
        except LLMProviderUnavailableError:
            raise
        except Exception as exc:
            raise LLMNetworkError("Model discovery network failure.", detail=str(exc)) from exc

        raw_models = data.get("data") if isinstance(data, dict) else None
        if not isinstance(raw_models, list):
            return []
        return [
            LLMModel(
                id=str(item.get("id")),
                name=str(item.get("id")),
                local=self.config.provider == "llama_cpp",
            )
            for item in raw_models
            if isinstance(item, dict) and item.get("id")
        ]

    async def chat(self, request: LLMChatRequest) -> LLMChatResponse:
        model = request.model or self.config.model
        if not model:
            raise LLMConfigError("Model is required.")
        payload = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": (
                request.temperature
                if request.temperature is not None
                else self.config.temperature
            ),
            "max_tokens": (
                request.max_tokens
                if request.max_tokens is not None
                else self.config.max_tokens
            ),
            "stream": False,
        }
        if request.response_format:
            payload["response_format"] = request.response_format
        url = f"{self.config.api_base.rstrip('/')}/chat/completions"
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        session = await self._session()
        try:
            async with session.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            ) as response:
                if response.status in {401, 403}:
                    raise LLMProviderUnavailableError("Invalid API key or unauthorized.")
                if response.status == 404:
                    raise LLMProviderUnavailableError("Chat endpoint or model not found.")
                if response.status >= 400:
                    text = await response.text()
                    raise LLMProviderUnavailableError(
                        f"Chat failed with HTTP {response.status}.",
                        detail=text[:300],
                    )
                data = await response.json()
        except LLMProviderUnavailableError:
            raise
        except Exception as exc:
            raise LLMNetworkError("Chat network failure.", detail=str(exc)) from exc

        choices = data.get("choices") if isinstance(data, dict) else []
        first = choices[0] if choices else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        return LLMChatResponse(
            provider=self.config.provider,
            model=model,
            content=str(content or ""),
            raw=data if isinstance(data, dict) else {},
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.organization:
            headers["OpenAI-Organization"] = self.config.organization
        if self.config.project:
            headers["OpenAI-Project"] = self.config.project
        return headers
