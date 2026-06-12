from __future__ import annotations

import asyncio

from backend.infrastructure.ai.base import LLMChatRequest, LLMProviderConfig
from backend.infrastructure.ai.factory import create_llm_client
from backend.infrastructure.ai.llama_cpp_server import shared_llama_cpp_server
from backend.infrastructure.ai.ollama_server import default_ollama_api_base, shared_ollama_server
from backend.modules.ai.schemas import LLMProfile


def _client_config_from_profile(profile: LLMProfile) -> LLMProviderConfig:
    import re

    from backend.modules.ai.service import PROVIDERS

    model = profile.model
    if not model and profile.provider == "llama_cpp" and profile.llama_config.model_path:
        model = re.sub(r"\.gguf$", "", profile.llama_config.model_path.rsplit("/", 1)[-1])
    return LLMProviderConfig(
        provider=profile.provider,  # type: ignore[arg-type]
        api_base=profile.api_base or PROVIDERS[profile.provider].default_api_base,
        api_key="",
        model=model,
        timeout_seconds=profile.timeout_seconds,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        streaming=profile.streaming,
        vision=profile.vision_support,
    )


async def ensure_profile_ready(profile: LLMProfile) -> None:
    shared_ollama_server.ensure_running(default_ollama_api_base("http://localhost:11434"))

    if profile.provider == "ollama":
        api_base = default_ollama_api_base(profile.api_base)
        shared_ollama_server.ensure_running(api_base)
        await _wait_for_ollama(api_base)
        return

    if profile.provider != "llama_cpp":
        return

    command = profile.llama_command.strip()
    if not command:
        return

    api_base = profile.api_base or profile.llama_config.api_base
    if shared_llama_cpp_server.is_api_reachable(api_base):
        return

    shared_llama_cpp_server.start(profile)
    await _wait_for_llama_cpp(api_base)


async def _wait_for_ollama(api_base: str, attempts: int = 20, delay_seconds: float = 1.0) -> None:
    for _ in range(attempts):
        if shared_ollama_server.is_reachable(api_base):
            return
        await asyncio.sleep(delay_seconds)
    if not shared_ollama_server.is_reachable(api_base):
        raise RuntimeError("Ollama server did not become reachable.")


async def _wait_for_llama_cpp(api_base: str, attempts: int = 30, delay_seconds: float = 1.0) -> None:
    client = create_llm_client(
        LLMProviderConfig(
            provider="llama_cpp",
            api_base=api_base,
            model="",
            timeout_seconds=30,
        )
    )
    last_error: Exception | None = None
    for _ in range(attempts):
        if shared_llama_cpp_server.is_api_reachable(api_base):
            return
        try:
            health = await client.health_check()
            if health.ok:
                return
        except Exception as exc:
            last_error = exc
        await asyncio.sleep(delay_seconds)
    if last_error:
        raise last_error
    raise RuntimeError("llama-server did not become reachable.")


async def chat_with_profile(profile: LLMProfile, request: LLMChatRequest):
    await ensure_profile_ready(profile)
    client = create_llm_client(_client_config_from_profile(profile))
    return await client.chat(request)

