from __future__ import annotations

from backend.infrastructure.ai.base import BaseLLMClient, LLMProviderConfig
from backend.infrastructure.ai.ollama_client import OllamaClient
from backend.infrastructure.ai.openai_compatible_client import OpenAICompatibleClient


def create_llm_client(config: LLMProviderConfig) -> BaseLLMClient:
    if config.provider == "ollama":
        return OllamaClient(config)
    if config.provider in {
        "openai",
        "openai_compatible",
        "llama_cpp",
        "huggingface",
        "custom_http",
    }:
        return OpenAICompatibleClient(config)
    if config.provider == "anthropic":
        raise ValueError("Anthropic provider is listed but not implemented in this build.")
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
