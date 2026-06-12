import type { LlmProfile, LlmProviderId, LlmProviderSettings, LlmTaskName } from "./api/settingsApi";

export const PROVIDER_IDS: LlmProviderId[] = [
  "openai",
  "openai_compatible",
  "ollama",
  "llama_cpp",
  "huggingface",
  "custom_http",
];

export const PROVIDER_LABELS: Record<LlmProviderId, string> = {
  openai: "OpenAI",
  openai_compatible: "OpenAI-compatible",
  ollama: "Ollama",
  llama_cpp: "llama.cpp",
  huggingface: "HuggingFace",
  custom_http: "Custom OpenAI-compatible",
};

export const TASK_LABELS: Record<LlmTaskName, string> = {
  assistant: "General AI assistant",
  mission_planning: "Mission planning",
  private_patrol: "Private patrol analysis",
  alert_explanation: "Alert explanation",
  video_summary: "Video/object summary",
  telemetry_anomaly: "Telemetry anomaly",
  offline_report: "Offline report",
};

const defaultProviderSettings = (
  apiBase: string,
  enabled = false,
  timeoutSeconds = 60,
): LlmProviderSettings => ({
  enabled,
  api_base: apiBase,
  model: "",
  has_api_key: false,
  api_key: "",
  organization: "",
  project: "",
  timeout_seconds: timeoutSeconds,
  max_tokens: 2048,
  temperature: 0.2,
  streaming: true,
  vision: false,
  embedding_model: "",
  context_window: 8192,
  mode: "external_server",
  server_binary_path: "",
  model_path: "",
  host: "127.0.0.1",
  port: 8080,
  gpu_layers: 0,
  threads: 0,
  batch_size: 512,
});

export const DEFAULT_AI_PROVIDERS: Record<LlmProviderId, LlmProviderSettings> = {
  openai: defaultProviderSettings("https://api.openai.com/v1", true),
  openai_compatible: defaultProviderSettings("", false),
  ollama: defaultProviderSettings("http://localhost:11434", true, 120),
  llama_cpp: defaultProviderSettings("http://127.0.0.1:8080/v1", false, 120),
  huggingface: defaultProviderSettings("https://router.huggingface.co/v1", false),
  custom_http: defaultProviderSettings("", false),
};

export const DEFAULT_TASK_DEFAULTS: Record<
  LlmTaskName,
  { provider: LlmProviderId | ""; model: string }
> = {
  assistant: { provider: "ollama", model: "" },
  mission_planning: { provider: "openai", model: "" },
  private_patrol: { provider: "ollama", model: "" },
  alert_explanation: { provider: "ollama", model: "" },
  video_summary: { provider: "ollama", model: "" },
  telemetry_anomaly: { provider: "ollama", model: "" },
  offline_report: { provider: "ollama", model: "" },
};

export const DEFAULT_LLM_PROFILES: LlmProfile[] = [
  {
    id: "ollama",
    name: "Local Ollama",
    provider: "ollama",
    api_base: "http://localhost:11434",
    model: "",
    enabled: true,
    has_api_key: false,
    api_key: null,
    timeout_seconds: 120,
    temperature: 0.2,
    max_tokens: 2048,
    context_window: 8192,
    streaming: true,
    vision_support: true,
    privacy_mode: "local",
    llama_connection_mode: "external_server",
    llama_command: "",
    llama_config: {
      binary_path: "",
      model_path: "",
      host: "127.0.0.1",
      port: 8080,
      api_base: "http://127.0.0.1:8080/v1",
      context_window: 8192,
      gpu_layers: 0,
      flash_attention: false,
      parallel_slots: 1,
      threads: 0,
      batch_size: 512,
      extra_allowed_args: [],
    },
  },
];
