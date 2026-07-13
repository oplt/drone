from __future__ import annotations

from typing import Any

from backend.infrastructure.ai.base import BaseLLMClient, LLMProviderConfig
from backend.infrastructure.ai.ollama_client import OllamaClient
from backend.infrastructure.ai.openai_compatible_client import OpenAICompatibleClient


def create_llm_client(
    config: LLMProviderConfig,
    *,
    session_registry: Any | None = None,
) -> BaseLLMClient:
    if config.provider == "ollama":
        return OllamaClient(config, session_registry=session_registry)
    if config.provider in {
        "openai",
        "openai_compatible",
        "llama_cpp",
        "huggingface",
        "custom_http",
    }:
        return OpenAICompatibleClient(config, session_registry=session_registry)
    if config.provider == "anthropic":
        raise ValueError("Anthropic provider is listed but not implemented in this build.")
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
