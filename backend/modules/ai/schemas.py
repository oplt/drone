from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.infrastructure.ai.base import LLMChatResponse, LLMHealth, LLMMessage, LLMModel

LLMTaskName = Literal[
    "assistant",
    "mission_planning",
    "private_patrol",
    "alert_explanation",
    "video_summary",
    "telemetry_anomaly",
    "offline_report",
    "warehouse_scan",
    "warehouse_inspection",
    "field_survey",
    "livestock",
]


class LLMProviderDescriptor(BaseModel):
    id: str
    label: str
    mode: Literal["cloud", "local", "custom"]
    default_api_base: str
    api_key_required: bool = False
    supports_model_discovery: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False


class LLMProviderSettings(BaseModel):
    enabled: bool = True
    api_base: str = ""
    model: str = ""
    has_api_key: bool = False
    api_key: str | None = None
    organization: str = ""
    project: str = ""
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    max_tokens: int = Field(default=2048, ge=1, le=262_144)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    streaming: bool = True
    vision: bool = False
    embedding_model: str = ""
    context_window: int = Field(default=8192, ge=1, le=1_000_000)
    mode: Literal["external_server", "managed_server"] = "external_server"
    server_binary_path: str = ""
    model_path: str = ""
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    gpu_layers: int = Field(default=0, ge=0)
    threads: int = Field(default=0, ge=0)
    batch_size: int = Field(default=512, ge=1)


class LlamaCppParsedConfig(BaseModel):
    binary_path: str = ""
    model_path: str = ""
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    api_base: str = "http://127.0.0.1:8080/v1"
    context_window: int = Field(default=8192, ge=1, le=1_000_000)
    gpu_layers: int = Field(default=0, ge=0)
    flash_attention: bool = False
    parallel_slots: int = Field(default=1, ge=1)
    threads: int = Field(default=0, ge=0)
    batch_size: int = Field(default=512, ge=1)
    extra_allowed_args: list[str] = Field(default_factory=list)


class LLMProfile(BaseModel):
    id: str
    name: str
    provider: str
    api_base: str = ""
    model: str = ""
    enabled: bool = True
    has_api_key: bool = False
    api_key: str | None = None
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=262_144)
    context_window: int = Field(default=8192, ge=1, le=1_000_000)
    streaming: bool = True
    vision_support: bool = False
    privacy_mode: Literal["local", "cloud"] = "local"
    llama_connection_mode: Literal[
        "external_server", "managed_command", "expert_parsed_settings"
    ] = "external_server"
    llama_command: str = ""
    llama_config: LlamaCppParsedConfig = Field(default_factory=LlamaCppParsedConfig)
    created_at: str = ""
    updated_at: str = ""


class LLMProfileCreate(BaseModel):
    name: str
    provider: str
    api_base: str = ""
    model: str = ""
    enabled: bool = True
    api_key: str | None = None
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=262_144)
    context_window: int = Field(default=8192, ge=1, le=1_000_000)
    streaming: bool = True
    vision_support: bool = False
    llama_connection_mode: Literal[
        "external_server", "managed_command", "expert_parsed_settings"
    ] = "external_server"
    llama_command: str = ""
    llama_config: LlamaCppParsedConfig = Field(default_factory=LlamaCppParsedConfig)


class LLMProfileUpdate(LLMProfileCreate):
    has_api_key: bool = False


class LLMProfilesResponse(BaseModel):
    profiles: list[LLMProfile]
    default_profile_id: str = ""


class LLMRoutingSettings(BaseModel):
    default_profile_id: str = ""
    task_overrides: dict[LLMTaskName, str] = Field(default_factory=dict)


class LLMRoutingUpdate(LLMRoutingSettings):
    pass


class LlamaCppServerStatus(BaseModel):
    running: bool
    profile_id: str | None = None
    pid: int | None = None
    command: list[str] = Field(default_factory=list)
    detail: str = ""


class LlamaCppCommandRequest(BaseModel):
    command: str


class LlamaCppCommandResponse(BaseModel):
    command: str
    config: LlamaCppParsedConfig
    summary: dict[str, str]


class LLMTaskDefault(BaseModel):
    provider: str = ""
    model: str = ""


class LLMSettingsResponse(BaseModel):
    active_provider: str = "ollama"
    system_prompt: str = ""
    providers: dict[str, LLMProviderSettings] = Field(default_factory=dict)
    task_defaults: dict[LLMTaskName, LLMTaskDefault] = Field(default_factory=dict)
    profiles: list[LLMProfile] = Field(default_factory=list)
    default_profile_id: str = ""
    task_overrides: dict[LLMTaskName, str] = Field(default_factory=dict)


class LLMSettingsUpdate(BaseModel):
    active_provider: str = "ollama"
    system_prompt: str = ""
    providers: dict[str, LLMProviderSettings] = Field(default_factory=dict)
    task_defaults: dict[LLMTaskName, LLMTaskDefault] = Field(default_factory=dict)
    profiles: list[LLMProfile] = Field(default_factory=list)
    default_profile_id: str = ""
    task_overrides: dict[LLMTaskName, str] = Field(default_factory=dict)


class LLMConnectionTestRequest(BaseModel):
    provider: str | None = None
    settings: LLMProviderSettings | None = None


class LLMChatTestRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    messages: list[LLMMessage] = Field(
        default_factory=lambda: [LLMMessage(role="user", content="Reply with: ok")]
    )


class LLMModelsResponse(BaseModel):
    provider: str
    models: list[LLMModel]


class LLMProvidersResponse(BaseModel):
    providers: list[LLMProviderDescriptor]


class LLMHealthResponse(LLMHealth):
    pass


class LLMChatTestResponse(LLMChatResponse):
    pass
