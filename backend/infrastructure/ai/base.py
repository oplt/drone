from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

LLMProviderType = Literal[
    "openai",
    "openai_compatible",
    "anthropic",
    "ollama",
    "llama_cpp",
    "huggingface",
    "custom_http",
]


class LLMProviderConfig(BaseModel):
    provider: LLMProviderType
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=262_144)
    streaming: bool = True
    vision: bool = False
    organization: str = ""
    project: str = ""


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMChatRequest(BaseModel):
    messages: list[LLMMessage]
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False


class LLMChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMModel(BaseModel):
    id: str
    name: str
    local: bool = False
    vision: bool = False


class LLMHealth(BaseModel):
    ok: bool
    status: Literal["running", "configured", "unreachable", "error", "not_configured"]
    detail: str = ""
    provider: str
    model_count: int | None = None


class BaseLLMClient(ABC):
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config

    @abstractmethod
    async def health_check(self) -> LLMHealth:
        raise NotImplementedError

    @abstractmethod
    async def list_models(self) -> list[LLMModel]:
        raise NotImplementedError

    @abstractmethod
    async def chat(self, request: LLMChatRequest) -> LLMChatResponse:
        raise NotImplementedError

    async def stream_chat(self, request: LLMChatRequest) -> AsyncIterator[str]:
        response = await self.chat(request)
        yield response.content
