import { httpRequest } from "../../../shared/api/httpClient";
import type {
  WarehouseMissionDefaultsResponse,
  WarehouseMissionLaunchResponse,
  WarehouseScanStartRequest,
  WarehouseScannedMapResponse,
} from "../types/missions";

export async function startWarehouseScan(
  payload: WarehouseScanStartRequest,
  token?: string | null,
): Promise<WarehouseMissionLaunchResponse> {
  return httpRequest<WarehouseMissionLaunchResponse>("/warehouse/missions/start", {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function listWarehouseScannedMaps(
  token?: string | null,
  fieldId?: number | null,
): Promise<WarehouseScannedMapResponse[]> {
  const params = new URLSearchParams();
  if (typeof fieldId === "number" && Number.isFinite(fieldId)) {
    params.set("field_id", String(fieldId));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return httpRequest<WarehouseScannedMapResponse[]>(`/warehouse/scanned-maps${suffix}`, {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function fetchWarehouseMissionDefaults(
  token?: string | null,
): Promise<WarehouseMissionDefaultsResponse> {
  return httpRequest<WarehouseMissionDefaultsResponse>("/warehouse/mission-defaults", {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function updateWarehouseMissionDefaults(
  payload: WarehouseMissionDefaultsResponse,
  token?: string | null,
): Promise<WarehouseMissionDefaultsResponse> {
  return httpRequest<WarehouseMissionDefaultsResponse>("/warehouse/mission-defaults", {
    method: "PUT",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}
