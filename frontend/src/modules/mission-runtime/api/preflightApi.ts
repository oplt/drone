import { httpRequest } from "../../../shared/api/httpClient";

export type PreflightSettings = Record<string, number | boolean | string | null | undefined>;

export async function fetchPreflightSettings(
  token?: string | null,
): Promise<PreflightSettings> {
  const data = await httpRequest<{ preflight?: PreflightSettings }>("/api/settings", {
    token,
    skipUnauthorizedRedirect: true,
  });
  return data?.preflight && typeof data.preflight === "object" ? data.preflight : {};
}
