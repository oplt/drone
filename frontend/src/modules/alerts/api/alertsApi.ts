import { httpRequest } from "../../../shared/api/httpClient";
import type { AlertItem } from "../types";

export async function fetchOpenAlertCount(token?: string | null): Promise<number> {
  const data = await httpRequest<{ open_count?: number }>("/api/alerts/open-count", { token });
  return Number.isFinite(data?.open_count) ? Number(data.open_count) : 0;
}

export async function fetchActiveAlerts(token?: string | null): Promise<AlertItem[]> {
  const data = await httpRequest<{ items?: AlertItem[] }>(
    "/api/alerts?status=active&limit=50",
    { token },
  );
  return Array.isArray(data?.items) ? data.items : [];
}

export async function acknowledgeAlert(
  alertId: number,
  token?: string | null,
): Promise<AlertItem> {
  return httpRequest<AlertItem>(`/api/alerts/${alertId}/ack`, {
    method: "POST",
    token,
  });
}

export async function resolveAlert(alertId: number, token?: string | null): Promise<AlertItem> {
  return httpRequest<AlertItem>(`/api/alerts/${alertId}/resolve`, {
    method: "POST",
    token,
  });
}
