from __future__ import annotations

import json
import re
import secrets
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from backend.infrastructure.ai.base import LLMChatRequest, LLMProviderConfig
from backend.infrastructure.ai.errors import LLMError
from backend.infrastructure.ai.factory import create_llm_client
from backend.infrastructure.ai.llama_cpp_server import (
    DEFAULT_LLAMA_API_BASE,
    parse_llama_cpp_command,
    shared_llama_cpp_server,
)
from backend.infrastructure.ai.local_llm_runtime import ensure_profile_ready
from backend.infrastructure.cache.redis import get_redis_client
from backend.modules.ai.schemas import (
    LlamaCppCommandRequest,
    LlamaCppCommandResponse,
    LlamaCppParsedConfig,
    LlamaCppServerStatus,
    LLMChatTestRequest,
    LLMConnectionTestRequest,
    LLMProfile,
    LLMProfileCreate,
    LLMProfilesResponse,
    LLMProfileUpdate,
    LLMProviderDescriptor,
    LLMProviderSettings,
    LLMRoutingSettings,
    LLMRoutingUpdate,
    LLMSettingsResponse,
    LLMSettingsUpdate,
    LLMTaskDefault,
    LLMTaskName,
)
from backend.modules.settings.repository import MASK, SettingsRepository

PROVIDERS: dict[str, LLMProviderDescriptor] = {
    "openai": LLMProviderDescriptor(
        id="openai",
        label="OpenAI",
        mode="cloud",
        default_api_base="https://api.openai.com/v1",
        api_key_required=True,
        supports_vision=True,
    ),
    "openai_compatible": LLMProviderDescriptor(
        id="openai_compatible",
        label="OpenAI-compatible",
        mode="cloud",
        default_api_base="",
        api_key_required=False,
        supports_vision=True,
    ),
    "ollama": LLMProviderDescriptor(
        id="ollama",
        label="Ollama",
        mode="local",
        default_api_base="http://localhost:11434",
        supports_vision=True,
    ),
    "llama_cpp": LLMProviderDescriptor(
        id="llama_cpp",
        label="llama.cpp server",
        mode="local",
        default_api_base=DEFAULT_LLAMA_API_BASE,
    ),
    "huggingface": LLMProviderDescriptor(
        id="huggingface",
        label="HuggingFace",
        mode="cloud",
        default_api_base="https://router.huggingface.co/v1",
        api_key_required=True,
        supports_vision=True,
    ),
    "custom_http": LLMProviderDescriptor(
        id="custom_http",
        label="Custom OpenAI-compatible",
        mode="custom",
        default_api_base="",
    ),
}

TASK_DEFAULTS: dict[str, LLMTaskDefault] = {
    "assistant": LLMTaskDefault(provider="ollama"),
    "mission_planning": LLMTaskDefault(provider="openai"),
    "private_patrol": LLMTaskDefault(provider="ollama"),
    "alert_explanation": LLMTaskDefault(provider="ollama"),
    "video_summary": LLMTaskDefault(provider="ollama"),
    "telemetry_anomaly": LLMTaskDefault(provider="ollama"),
    "offline_report": LLMTaskDefault(provider="ollama"),
    "warehouse_scan": LLMTaskDefault(provider="ollama"),
    "warehouse_inspection": LLMTaskDefault(provider="ollama"),
    "field_survey": LLMTaskDefault(provider="openai"),
    "livestock": LLMTaskDefault(provider="ollama"),
}


def default_llm_settings() -> dict[str, Any]:
    return {
        "active_provider": "ollama",
        "system_prompt": "You support drone operations. Be precise and operationally safe.",
        "providers": {
            provider_id: {
                "enabled": provider_id in {"ollama", "openai"},
                "api_base": descriptor.default_api_base,
                "model": "",
                "timeout_seconds": 120 if descriptor.mode == "local" else 60,
                "max_tokens": 2048,
                "temperature": 0.2,
                "streaming": descriptor.supports_streaming,
                "vision": descriptor.supports_vision,
                "context_window": 8192,
                "mode": "external_server",
                "server_binary_path": "",
                "model_path": "",
                "host": "127.0.0.1",
                "port": 8080,
                "gpu_layers": 0,
                "threads": 0,
                "batch_size": 512,
            }
            for provider_id, descriptor in PROVIDERS.items()
        },
        "task_defaults": {key: value.model_dump() for key, value in TASK_DEFAULTS.items()},
        "profiles": [],
        "default_profile_id": "",
        "task_overrides": {},
        "agents": {
            "enabled": True,
            "private_patrol": True,
            "property_patrol": True,
            "warehouse_scan": True,
            "warehouse_inspection": True,
            "field_survey": True,
            "livestock": True,
            "assistant": True,
        },
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"llm-{secrets.token_hex(4)}"


class AISettingsService:
    SETTINGS_CACHE_TTL_SECONDS = 30.0
    SHARED_SETTINGS_TTL_SECONDS = 60
    _PUBLIC_SETTINGS_KEY = "ai:settings:v1:public"
    _PROVIDER_CACHE_PREFIX = "ai:provider-cache:v1"

    def __init__(self, repo: SettingsRepository | None = None) -> None:
        self.repo = repo or SettingsRepository()
        self._settings_cache: dict[bool, tuple[float, LLMSettingsResponse]] = {}
        self._cache_revision = 0

    async def get_settings(self, *, effective: bool = False) -> LLMSettingsResponse:
        # Effective settings contain decrypted provider secrets. Keep them out of
        # Redis and out of process-local caches; the safe public routing document
        # is the shared read-through cache.
        if not effective:
            cached_shared = await self._get_shared_public_settings()
            if cached_shared is not None:
                result = LLMSettingsResponse.model_validate(cached_shared)
                self._settings_cache[effective] = (time.monotonic(), result)
                return result.model_copy(deep=True)
        cached = self._settings_cache.get(effective)
        if (
            cached is not None
            and not effective
            and time.monotonic() - cached[0] < self.SETTINGS_CACHE_TTL_SECONDS
        ):
            return cached[1].model_copy(deep=True)
        doc = (
            await self.repo.get_effective_settings_doc()
            if effective
            else await self.repo.get_settings_doc()
        )
        normalized = self._normalize_ai(doc.get("ai", {}), include_secret=effective)
        result = LLMSettingsResponse.model_validate(normalized)
        if not effective:
            self._settings_cache[effective] = (time.monotonic(), result)
            await self._set_shared_public_settings(normalized)
        return result.model_copy(deep=True)

    def cache_revision(self) -> int:
        return self._cache_revision

    async def shared_cache_revision(self) -> int:
        try:
            value = await get_redis_client().get("ai:settings:v1:revision")
            return int(value or 0)
        except Exception:
            return self._cache_revision

    def invalidate_cache(self) -> None:
        self._settings_cache.clear()
        self._cache_revision += 1

    async def invalidate_shared_cache(self) -> None:
        """Invalidate routing/model caches after any settings write."""
        self.invalidate_cache()
        try:
            redis = get_redis_client()
            await redis.delete(self._PUBLIC_SETTINGS_KEY)
            await redis.incr("ai:settings:v1:revision")
            keys = [
                key async for key in redis.scan_iter(match=f"{self._PROVIDER_CACHE_PREFIX}:*")
            ]
            if keys:
                await redis.delete(*keys)
        except Exception:
            # PostgreSQL/Vault remains authoritative when Redis is unavailable.
            return

    async def _get_shared_public_settings(self) -> dict[str, Any] | None:
        try:
            raw = await get_redis_client().get(self._PUBLIC_SETTINGS_KEY)
            if not raw:
                return None
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    async def _set_shared_public_settings(self, value: dict[str, Any]) -> None:
        try:
            await get_redis_client().set(
                self._PUBLIC_SETTINGS_KEY,
                json.dumps(value, separators=(",", ":"), default=str),
                ex=self.SHARED_SETTINGS_TTL_SECONDS,
            )
        except Exception:
            return

    async def save_settings(self, payload: LLMSettingsUpdate) -> LLMSettingsResponse:
        public_doc = await self.repo.get_settings_doc()
        normalized = self._normalize_ai(payload.model_dump(), include_secret=True)
        self._validate_settings(normalized)
        public_doc["ai"] = normalized
        await self.repo.put_settings_doc(public_doc)
        await self.invalidate_shared_cache()
        return await self.get_settings()

    async def list_profiles(self) -> LLMProfilesResponse:
        settings = await self.get_settings()
        return LLMProfilesResponse(
            profiles=settings.profiles,
            default_profile_id=settings.default_profile_id,
        )

    async def create_profile(self, payload: LLMProfileCreate) -> LLMProfile:
        settings = await self.get_settings(effective=True)
        profile_ids = {profile.id for profile in settings.profiles}
        profile_id = _slugify(payload.name)
        if profile_id in profile_ids:
            profile_id = f"{profile_id}-{secrets.token_hex(3)}"
        timestamp = _now_iso()
        profile = LLMProfile(
            id=profile_id,
            **payload.model_dump(),
            privacy_mode=self._privacy_for_provider(payload.provider),
            has_api_key=bool(payload.api_key),
            created_at=timestamp,
            updated_at=timestamp,
        )
        profile = self._prepare_profile(profile)
        updated_profiles = [*settings.profiles, profile]
        default_profile_id = settings.default_profile_id or profile.id
        await self._save_profiles(updated_profiles, default_profile_id, settings.task_overrides)
        return (await self.get_profile(profile.id))

    async def get_profile(self, profile_id: str, *, effective: bool = False) -> LLMProfile:
        settings = await self.get_settings(effective=effective)
        for profile in settings.profiles:
            if profile.id == profile_id:
                return profile
        raise ValueError(f"Unknown LLM profile: {profile_id}")

    async def resolve_profile_for_task(self, task: LLMTaskName) -> LLMProfile | None:
        """Resolve the effective profile for a mission/agent task."""
        if task not in TASK_DEFAULTS:
            raise ValueError(f"Unsupported LLM task: {task}")
        settings = await self.get_settings(effective=True)
        override_id = (settings.task_overrides or {}).get(task)
        if override_id:
            for profile in settings.profiles:
                if profile.id == override_id and profile.enabled:
                    return profile
        default_id = str(settings.default_profile_id or "").strip()
        if default_id:
            for profile in settings.profiles:
                if profile.id == default_id and profile.enabled:
                    return profile
        task_default = settings.task_defaults.get(task)
        if task_default is not None:
            provider_settings = settings.providers.get(task_default.provider)
            if provider_settings is not None and provider_settings.enabled:
                for profile in settings.profiles:
                    if (
                        profile.enabled
                        and profile.provider == task_default.provider
                        and (not task_default.model or profile.model == task_default.model)
                    ):
                        return profile
        return None

    async def update_profile(self, profile_id: str, payload: LLMProfileUpdate) -> LLMProfile:
        settings = await self.get_settings(effective=True)
        timestamp = _now_iso()
        updated: list[LLMProfile] = []
        found = False
        for profile in settings.profiles:
            if profile.id != profile_id:
                updated.append(profile)
                continue
            found = True
            raw = profile.model_dump()
            incoming = payload.model_dump()
            if not str(incoming.get("api_key") or "").strip() and (
                profile.has_api_key or incoming.get("has_api_key")
            ):
                incoming["has_api_key"] = True
                if profile.api_key:
                    incoming["api_key"] = MASK
            raw.update(incoming)
            raw["id"] = profile_id
            raw["privacy_mode"] = self._privacy_for_provider(str(raw.get("provider") or ""))
            raw["created_at"] = profile.created_at or timestamp
            raw["updated_at"] = timestamp
            updated.append(self._prepare_profile(LLMProfile.model_validate(raw)))
        if not found:
            raise ValueError(f"Unknown LLM profile: {profile_id}")
        await self._save_profiles(updated, settings.default_profile_id, settings.task_overrides)
        return await self.get_profile(profile_id)

    async def delete_profile(self, profile_id: str) -> None:
        settings = await self.get_settings(effective=True)
        updated = [profile for profile in settings.profiles if profile.id != profile_id]
        if len(updated) == len(settings.profiles):
            raise ValueError(f"Unknown LLM profile: {profile_id}")
        default_profile_id = settings.default_profile_id
        if default_profile_id == profile_id:
            default_profile_id = updated[0].id if updated else ""
        overrides = {
            task: routed_id
            for task, routed_id in settings.task_overrides.items()
            if routed_id != profile_id
        }
        await self._save_profiles(updated, default_profile_id, overrides)

    async def get_routing(self) -> LLMRoutingSettings:
        settings = await self.get_settings()
        return LLMRoutingSettings(
            default_profile_id=settings.default_profile_id,
            task_overrides=settings.task_overrides,
        )

    async def save_routing(self, payload: LLMRoutingUpdate) -> LLMRoutingSettings:
        settings = await self.get_settings(effective=True)
        profile_ids = {profile.id for profile in settings.profiles}
        if payload.default_profile_id and payload.default_profile_id not in profile_ids:
            raise ValueError("Default LLM profile does not exist.")
        for task, profile_id in payload.task_overrides.items():
            if task not in TASK_DEFAULTS:
                raise ValueError(f"Unsupported task: {task}")
            if profile_id and profile_id not in profile_ids:
                raise ValueError(f"Task route profile does not exist: {profile_id}")
        await self._save_profiles(
            settings.profiles,
            payload.default_profile_id,
            {task: value for task, value in payload.task_overrides.items() if value},
        )
        return await self.get_routing()

    async def list_profile_models(self, profile_id: str):
        profile = await self.get_profile(profile_id, effective=True)
        await ensure_profile_ready(profile)
        cache_key = f"{self._PROVIDER_CACHE_PREFIX}:models:profile:{profile_id}"
        cached = await self._get_json_cache(cache_key)
        if isinstance(cached, list):
            from backend.infrastructure.ai.base import LLMModel

            return [LLMModel.model_validate(item) for item in cached]
        client = create_llm_client(self._client_config_from_profile(profile))
        models = await client.list_models()
        await self._set_json_cache(
            cache_key,
            [model.model_dump(mode="json") for model in models],
            180,
        )
        return models

    async def test_profile(self, profile_id: str):
        profile = await self.get_profile(profile_id, effective=True)
        await ensure_profile_ready(profile)
        client = create_llm_client(self._client_config_from_profile(profile))
        # Explicit connection tests always bypass cached health and refresh it.
        return await client.health_check()

    async def start_llama_cpp_server(self, profile_id: str) -> LlamaCppServerStatus:
        profile = await self.get_profile(profile_id, effective=True)
        return shared_llama_cpp_server.start(profile)

    async def restart_llama_cpp_server(self, profile_id: str) -> LlamaCppServerStatus:
        profile = await self.get_profile(profile_id, effective=True)
        return shared_llama_cpp_server.restart(profile)

    async def stop_llama_cpp_server(self) -> LlamaCppServerStatus:
        return shared_llama_cpp_server.stop()

    async def llama_cpp_server_status(self) -> LlamaCppServerStatus:
        return shared_llama_cpp_server.status()

    async def parse_llama_cpp_command(
        self,
        request: LlamaCppCommandRequest,
    ) -> LlamaCppCommandResponse:
        return parse_llama_cpp_command(request.command)

    async def start_and_test_llama_cpp_server(self, profile_id: str) -> dict[str, Any]:
        profile = await self.get_profile(profile_id, effective=True)
        await ensure_profile_ready(profile)
        status = shared_llama_cpp_server.status()
        health = await self.test_profile(profile_id)
        return {"status": status, "health": health}

    async def list_models(self, provider: str):
        settings = await self.get_settings(effective=True)
        client = create_llm_client(self._client_config(provider, settings.providers[provider]))
        cache_key = f"{self._PROVIDER_CACHE_PREFIX}:models:provider:{provider}"
        cached = await self._get_json_cache(cache_key)
        if isinstance(cached, list):
            from backend.infrastructure.ai.base import LLMModel

            return [LLMModel.model_validate(item) for item in cached]
        models = await client.list_models()
        await self._set_json_cache(
            cache_key,
            [model.model_dump(mode="json") for model in models],
            180,
        )
        return models

    async def test_connection(self, request: LLMConnectionTestRequest):
        settings = await self.get_settings(effective=True)
        provider = request.provider or settings.active_provider
        provider_settings = request.settings or settings.providers.get(provider)
        if provider_settings is None:
            raise ValueError(f"Unknown LLM provider: {provider}")
        if provider == "ollama":
            profile = LLMProfile(
                id="runtime-ollama",
                name="runtime-ollama",
                provider="ollama",
                api_base=provider_settings.api_base,
                model=provider_settings.model,
            )
            await ensure_profile_ready(profile)
        client = create_llm_client(self._client_config(provider, provider_settings))
        return await client.health_check()

    async def chat_test(self, request: LLMChatTestRequest):
        settings = await self.get_settings(effective=True)
        provider = request.provider or settings.active_provider
        provider_settings = settings.providers.get(provider)
        if provider_settings is None:
            raise ValueError(f"Unknown LLM provider: {provider}")
        if provider == "ollama":
            profile = LLMProfile(
                id="runtime-ollama",
                name="runtime-ollama",
                provider="ollama",
                api_base=provider_settings.api_base,
                model=provider_settings.model,
            )
            await ensure_profile_ready(profile)
        client = create_llm_client(self._client_config(provider, provider_settings))
        return await client.chat(
            LLMChatRequest(
                messages=request.messages,
                model=request.model or provider_settings.model,
                temperature=provider_settings.temperature,
                max_tokens=min(provider_settings.max_tokens, 256),
            )
        )

    async def _save_profiles(
        self,
        profiles: list[LLMProfile],
        default_profile_id: str,
        task_overrides: dict[str, str],
    ) -> None:
        doc = await self.repo.get_settings_doc()
        ai = self._normalize_ai(doc.get("ai", {}), include_secret=False)
        ai["profiles"] = [profile.model_dump() for profile in profiles]
        ai["default_profile_id"] = default_profile_id
        ai["task_overrides"] = task_overrides
        doc["ai"] = ai
        await self.repo.put_settings_doc(doc)
        await self.invalidate_shared_cache()

    async def _get_json_cache(self, key: str) -> Any | None:
        try:
            raw = await get_redis_client().get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _set_json_cache(self, key: str, value: Any, ttl: int) -> None:
        try:
            await get_redis_client().set(key, json.dumps(value, separators=(",", ":")), ex=ttl)
        except Exception:
            return

    def _normalize_ai(self, raw: dict[str, Any], *, include_secret: bool) -> dict[str, Any]:
        defaults = default_llm_settings()
        source = deepcopy(raw or {})

        legacy_provider = str(source.get("llm_provider") or "").strip()
        legacy_base = str(source.get("llm_api_base") or "").strip()
        legacy_model = str(source.get("llm_model") or "").strip()
        legacy_key = source.get("llm_api_key")
        if legacy_provider and "providers" not in source:
            source["active_provider"] = legacy_provider
            source["providers"] = {
                legacy_provider: {
                    "api_base": legacy_base,
                    "model": legacy_model,
                    "api_key": legacy_key,
                    "has_api_key": bool(legacy_key and legacy_key != MASK),
                }
            }

        merged = deepcopy(defaults)
        merged.update({k: v for k, v in source.items() if k not in {"providers", "task_defaults"}})
        for provider_id, provider_settings in (source.get("providers") or {}).items():
            if provider_id in PROVIDERS and isinstance(provider_settings, dict):
                merged["providers"][provider_id].update(provider_settings)
        for task, task_default in (source.get("task_defaults") or {}).items():
            if task in TASK_DEFAULTS and isinstance(task_default, dict):
                merged["task_defaults"][task].update(task_default)
        profiles = self._normalize_profiles(source, merged, include_secret=include_secret)
        merged["profiles"] = [profile.model_dump() for profile in profiles]
        default_profile_id = str(source.get("default_profile_id") or "")
        if not default_profile_id and profiles:
            active = str(merged.get("active_provider") or "")
            default_profile_id = (
                active if any(profile.id == active for profile in profiles) else profiles[0].id
            )
        merged["default_profile_id"] = default_profile_id
        profile_ids = {profile.id for profile in profiles}
        raw_overrides = source.get("task_overrides") or {}
        merged["task_overrides"] = {
            task: profile_id
            for task, profile_id in raw_overrides.items()
            if task in TASK_DEFAULTS and profile_id in profile_ids
        }

        for provider_settings in merged["providers"].values():
            api_key = provider_settings.get("api_key")
            if api_key == "":
                provider_settings["has_api_key"] = False
            elif api_key and api_key != MASK:
                provider_settings["has_api_key"] = True
            else:
                provider_settings["has_api_key"] = bool(provider_settings.get("has_api_key"))
            if not include_secret:
                provider_settings["api_key"] = None
        active = str(merged.get("active_provider") or "ollama")
        merged["active_provider"] = active if active in PROVIDERS else "ollama"
        return merged

    def _normalize_profiles(
        self,
        source: dict[str, Any],
        merged: dict[str, Any],
        *,
        include_secret: bool,
    ) -> list[LLMProfile]:
        raw_profiles = source.get("profiles")
        profiles: list[LLMProfile] = []
        if isinstance(raw_profiles, list):
            for raw_profile in raw_profiles:
                if not isinstance(raw_profile, dict):
                    continue
                try:
                    profile = LLMProfile.model_validate(raw_profile)
                except Exception:
                    continue
                api_key = profile.api_key
                if api_key == "":
                    profile.has_api_key = False
                elif api_key and api_key != MASK:
                    profile.has_api_key = True
                profile.privacy_mode = self._privacy_for_provider(profile.provider)
                if not include_secret:
                    profile.api_key = None
                profiles.append(profile)
        if profiles:
            return profiles

        timestamp = _now_iso()
        for provider_id, provider_settings in merged.get("providers", {}).items():
            if provider_id not in PROVIDERS or not isinstance(provider_settings, dict):
                continue
            if not provider_settings.get("enabled") and not provider_settings.get("model"):
                continue
            descriptor = PROVIDERS[provider_id]
            profile = LLMProfile(
                id=provider_id,
                name=descriptor.label,
                provider=provider_id,
                api_base=str(provider_settings.get("api_base") or descriptor.default_api_base),
                model=str(provider_settings.get("model") or ""),
                enabled=bool(provider_settings.get("enabled", True)),
                has_api_key=bool(provider_settings.get("has_api_key")),
                api_key=provider_settings.get("api_key") if include_secret else None,
                timeout_seconds=float(provider_settings.get("timeout_seconds") or 60),
                temperature=float(provider_settings.get("temperature") or 0.2),
                max_tokens=int(provider_settings.get("max_tokens") or 2048),
                context_window=int(provider_settings.get("context_window") or 8192),
                streaming=bool(provider_settings.get("streaming", True)),
                vision_support=bool(provider_settings.get("vision", False)),
                privacy_mode=self._privacy_for_provider(provider_id),
                created_at=timestamp,
                updated_at=timestamp,
            )
            profiles.append(profile)
        return profiles

    def _validate_settings(self, data: dict[str, Any]) -> None:
        active = data.get("active_provider")
        if active not in PROVIDERS:
            raise ValueError("Unsupported active LLM provider.")
        for provider_id, provider_settings in data.get("providers", {}).items():
            if provider_id not in PROVIDERS:
                raise ValueError(f"Unsupported LLM provider: {provider_id}")
            if provider_settings.get("enabled"):
                api_base = str(provider_settings.get("api_base") or "").strip()
                parsed = urlparse(api_base)
                if not parsed.scheme or not parsed.netloc:
                    raise ValueError(f"{provider_id} API base must be an absolute URL.")
        for task, task_default in data.get("task_defaults", {}).items():
            provider = task_default.get("provider")
            if provider and provider not in PROVIDERS:
                raise ValueError(f"Unsupported task provider for {task}.")
        profile_ids = {profile.get("id") for profile in data.get("profiles", [])}
        default_profile_id = data.get("default_profile_id")
        if default_profile_id and default_profile_id not in profile_ids:
            raise ValueError("Default LLM profile does not exist.")
        for profile in data.get("profiles", []):
            provider = profile.get("provider")
            if provider not in PROVIDERS:
                raise ValueError(f"Unsupported LLM profile provider: {provider}")
            if profile.get("enabled"):
                api_base = str(profile.get("api_base") or "").strip()
                parsed = urlparse(api_base)
                if not parsed.scheme or not parsed.netloc:
                    name = profile.get("name") or provider
                    raise ValueError(f"{name} API base must be an absolute URL.")
            if provider == "llama_cpp":
                self._validate_llama_cpp_profile(profile)
            if provider == "huggingface" and profile.get("enabled"):
                if not str(profile.get("model") or "").strip():
                    name = profile.get("name") or provider
                    raise ValueError(f"{name} requires a HuggingFace model id.")
                if not profile.get("has_api_key") and not str(profile.get("api_key") or "").strip():
                    name = profile.get("name") or provider
                    raise ValueError(f"{name} requires a HuggingFace token.")
        for task, profile_id in data.get("task_overrides", {}).items():
            if task not in TASK_DEFAULTS:
                raise ValueError(f"Unsupported task: {task}")
            if profile_id and profile_id not in profile_ids:
                raise ValueError(f"Task route profile does not exist: {profile_id}")

    def _client_config(self, provider: str, settings: LLMProviderSettings) -> LLMProviderConfig:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM provider: {provider}")
        api_base = settings.api_base or PROVIDERS[provider].default_api_base
        api_key = "" if settings.api_key == MASK else str(settings.api_key or "")
        return LLMProviderConfig(
            provider=provider,  # type: ignore[arg-type]
            api_base=api_base,
            api_key=api_key,
            model=settings.model,
            timeout_seconds=settings.timeout_seconds,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            streaming=settings.streaming,
            vision=settings.vision,
            organization=settings.organization,
            project=settings.project,
        )

    def _client_config_from_profile(self, profile: LLMProfile) -> LLMProviderConfig:
        if profile.provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM provider: {profile.provider}")
        api_key = "" if profile.api_key == MASK else str(profile.api_key or "")
        model = profile.model
        if not model and profile.provider == "llama_cpp" and profile.llama_config.model_path:
            model = re.sub(r"\.gguf$", "", profile.llama_config.model_path.rsplit("/", 1)[-1])
        return LLMProviderConfig(
            provider=profile.provider,  # type: ignore[arg-type]
            api_base=profile.api_base or PROVIDERS[profile.provider].default_api_base,
            api_key=api_key,
            model=model,
            timeout_seconds=profile.timeout_seconds,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            streaming=profile.streaming,
            vision=profile.vision_support,
        )

    def _privacy_for_provider(self, provider: str) -> str:
        descriptor = PROVIDERS.get(provider)
        return "local" if descriptor and descriptor.mode == "local" else "cloud"

    def _prepare_profile(self, profile: LLMProfile) -> LLMProfile:
        raw = profile.model_dump()
        if raw.get("provider") == "llama_cpp":
            self._validate_llama_cpp_profile(raw)
        return LLMProfile.model_validate(raw)

    def _validate_llama_cpp_profile(self, profile: dict[str, Any]) -> None:
        command = str(profile.get("llama_command") or "").strip()
        if not command:
            profile["llama_connection_mode"] = "external_server"
            profile["llama_config"] = LlamaCppParsedConfig().model_dump()
            return

        parsed = parse_llama_cpp_command(command)
        profile["llama_command"] = command
        profile["llama_config"] = parsed.config.model_dump()
        profile["api_base"] = parsed.config.api_base
        profile["llama_connection_mode"] = "managed_command"
        profile["context_window"] = parsed.config.context_window
        if not profile.get("model"):
            profile["model"] = parsed.config.model_path.rsplit("/", 1)[-1].removesuffix(".gguf")


def llm_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, LLMError):
        return {"code": exc.code, "message": str(exc), "detail": exc.detail}
    return {"code": "LLM_REQUEST_FAILED", "message": str(exc), "detail": ""}
