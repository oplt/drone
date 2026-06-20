import { httpRequest } from "../../../shared/api/httpClient";

export type AppSettingsPayload = Record<string, unknown>;

export async function fetchAppSettings<T = AppSettingsPayload>(): Promise<T> {
  return httpRequest<T>("/api/settings");
}

export async function updateAppSettings<T = AppSettingsPayload>(
  payload: AppSettingsPayload,
): Promise<T> {
  return httpRequest<T>("/api/settings", {
    method: "PUT",
    body: payload,
  });
}

export async function uploadAppSettingsFile(
  formData: FormData,
): Promise<unknown> {
  return httpRequest("/api/settings/upload", {
    method: "POST",
    body: formData,
  });
}

export type LlmProviderId =
  | "openai"
  | "openai_compatible"
  | "ollama"
  | "llama_cpp"
  | "huggingface"
  | "custom_http";

export type LlmProviderSettings = {
  enabled: boolean;
  api_base: string;
  model: string;
  has_api_key?: boolean;
  api_key?: string | null;
  organization?: string;
  project?: string;
  timeout_seconds: number;
  max_tokens: number;
  temperature: number;
  streaming: boolean;
  vision: boolean;
  embedding_model?: string;
  context_window: number;
  mode?: "external_server" | "managed_server";
  server_binary_path?: string;
  model_path?: string;
  host?: string;
  port?: number;
  gpu_layers?: number;
  threads?: number;
  batch_size?: number;
};

export type LlmTaskName =
  | "assistant"
  | "mission_planning"
  | "private_patrol"
  | "alert_explanation"
  | "video_summary"
  | "telemetry_anomaly"
  | "offline_report"
  | "warehouse_scan"
  | "warehouse_inspection"
  | "field_survey"
  | "livestock";

export type LlmSettingsPayload = {
  active_provider: LlmProviderId;
  system_prompt: string;
  providers: Record<LlmProviderId, LlmProviderSettings>;
  task_defaults: Record<LlmTaskName, { provider: LlmProviderId | ""; model: string }>;
};

export type LlmProviderDescriptor = {
  id: LlmProviderId;
  label: string;
  mode: "cloud" | "local" | "custom";
  default_api_base: string;
  api_key_required: boolean;
  supports_model_discovery: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
};

export type LlmModel = { id: string; name: string; local: boolean; vision: boolean };

export type LlmProfile = {
  id: string;
  name: string;
  provider: LlmProviderId;
  api_base: string;
  model: string;
  enabled: boolean;
  has_api_key: boolean;
  api_key?: string | null;
  timeout_seconds: number;
  temperature: number;
  max_tokens: number;
  context_window: number;
  streaming: boolean;
  vision_support: boolean;
  privacy_mode: "local" | "cloud";
  llama_connection_mode: "external_server" | "managed_command" | "expert_parsed_settings";
  llama_command: string;
  llama_config: LlamaCppParsedConfig;
  created_at?: string;
  updated_at?: string;
};

export type LlmProfileInput = Omit<
  LlmProfile,
  "id" | "has_api_key" | "privacy_mode" | "created_at" | "updated_at"
> & { has_api_key?: boolean };

export type LlmRouting = {
  default_profile_id: string;
  task_overrides: Partial<Record<LlmTaskName, string>>;
};

export type LlamaCppServerStatus = {
  running: boolean;
  profile_id?: string | null;
  pid?: number | null;
  command: string[];
  detail: string;
};

export type LlamaCppParsedConfig = {
  binary_path: string;
  model_path: string;
  host: string;
  port: number;
  api_base: string;
  context_window: number;
  gpu_layers: number;
  flash_attention: boolean;
  parallel_slots: number;
  threads: number;
  batch_size: number;
  extra_allowed_args: string[];
};

export type LlamaCppCommandResponse = {
  command: string;
  config: LlamaCppParsedConfig;
  summary: Record<string, string>;
};

export async function fetchLlmProviders(): Promise<{ providers: LlmProviderDescriptor[] }> {
  return httpRequest("/api/ai/llm/providers");
}

export async function fetchLlmModels(provider: LlmProviderId): Promise<{ provider: string; models: LlmModel[] }> {
  return httpRequest(`/api/ai/llm/models?provider=${encodeURIComponent(provider)}`);
}

export async function testLlmConnection(provider: LlmProviderId): Promise<{
  ok: boolean;
  status: string;
  detail: string;
  provider: string;
  model_count?: number;
}> {
  return httpRequest("/api/ai/llm/test-connection", {
    method: "POST",
    body: { provider },
  });
}

export async function fetchLlmProfiles(): Promise<{
  profiles: LlmProfile[];
  default_profile_id: string;
}> {
  return httpRequest("/api/ai/llm/profiles");
}

export async function createLlmProfile(payload: LlmProfileInput): Promise<LlmProfile> {
  return httpRequest("/api/ai/llm/profiles", { method: "POST", body: payload });
}

export async function updateLlmProfile(
  profileId: string,
  payload: LlmProfileInput,
): Promise<LlmProfile> {
  return httpRequest(`/api/ai/llm/profiles/${encodeURIComponent(profileId)}`, {
    method: "PUT",
    body: payload,
  });
}

export async function deleteLlmProfile(profileId: string): Promise<void> {
  await httpRequest(`/api/ai/llm/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
}

export async function testLlmProfile(profileId: string): Promise<{
  ok: boolean;
  status: string;
  detail: string;
  provider: string;
  model_count?: number;
}> {
  return httpRequest(`/api/ai/llm/profiles/${encodeURIComponent(profileId)}/test`, {
    method: "POST",
  });
}

export async function fetchLlmProfileModels(
  profileId: string,
): Promise<{ provider: string; models: LlmModel[] }> {
  return httpRequest(`/api/ai/llm/profiles/${encodeURIComponent(profileId)}/models`);
}

export async function fetchLlmRouting(): Promise<LlmRouting> {
  return httpRequest("/api/ai/llm/routing");
}

export async function updateLlmRouting(payload: LlmRouting): Promise<LlmRouting> {
  return httpRequest("/api/ai/llm/routing", { method: "PUT", body: payload });
}

export async function startLlamaCppServer(profileId: string): Promise<LlamaCppServerStatus> {
  return httpRequest(
    `/api/ai/llm/profiles/${encodeURIComponent(profileId)}/llama-cpp/start`,
    { method: "POST" },
  );
}

export async function restartLlamaCppServer(profileId: string): Promise<LlamaCppServerStatus> {
  return httpRequest(
    `/api/ai/llm/profiles/${encodeURIComponent(profileId)}/llama-cpp/restart`,
    { method: "POST" },
  );
}

export async function startAndTestLlamaCppServer(profileId: string): Promise<{
  status: LlamaCppServerStatus;
  health: { ok: boolean; status: string; detail: string; provider: string; model_count?: number };
}> {
  return httpRequest(
    `/api/ai/llm/profiles/${encodeURIComponent(profileId)}/llama-cpp/start-test`,
    { method: "POST" },
  );
}

export async function stopLlamaCppServer(): Promise<LlamaCppServerStatus> {
  return httpRequest("/api/ai/llm/llama-cpp/stop", { method: "POST" });
}

export async function fetchLlamaCppServerStatus(): Promise<LlamaCppServerStatus> {
  return httpRequest("/api/ai/llm/llama-cpp/status");
}

export async function parseLlamaCppCommand(command: string): Promise<LlamaCppCommandResponse> {
  return httpRequest("/api/ai/llm/llama-cpp/parse-command", {
    method: "POST",
    body: { command },
  });
}
