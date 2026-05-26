import { httpRequest } from "../../../shared/api/httpClient";
import type { Herd, HerdAlert, HerdLatestPos, LivestockTaskType } from "../types";

export async function fetchHerds(token?: string | null): Promise<Herd[]> {
  return httpRequest<Herd[]>("/livestock/herds", { token });
}

export async function fetchHerdLatestPositions(
  herdId: number,
  token?: string | null,
): Promise<HerdLatestPos[]> {
  const data = await httpRequest<{ positions?: HerdLatestPos[] }>(
    `/livestock/herds/${herdId}/latest_positions`,
    { token },
  );
  return data.positions ?? [];
}

export async function fetchHerdRiskAlerts(
  herdId: number,
  token?: string | null,
): Promise<HerdAlert[]> {
  const data = await httpRequest<{ alerts?: HerdAlert[] }>(
    `/livestock/herds/${herdId}/risk`,
    { token },
  );
  return data.alerts ?? [];
}

export async function createLivestockTask(
  herdId: number,
  type: LivestockTaskType,
  params: Record<string, unknown>,
  token?: string | null,
): Promise<{ id: number }> {
  return httpRequest<{ id: number }>("/livestock/tasks", {
    method: "POST",
    body: { herd_id: herdId, type, params },
    token,
  });
}

export async function planLivestockTaskMission(
  taskId: number,
  token?: string | null,
): Promise<{ mission?: { waypoints?: Array<{ lat: number; lon: number; alt?: number }> } }> {
  return httpRequest(`/livestock/tasks/${taskId}/plan`, {
    method: "POST",
    token,
  });
}
