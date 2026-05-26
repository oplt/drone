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
