import { httpRequest } from "../../../shared/api/httpClient";
import type {
  CreateWarehouseMapPayload,
  CreateWarehouseSensorRigPayload,
  UpdateWarehouseSensorRigCalibrationPayload,
  WarehouseDockPayload,
  WarehouseDockStation,
  WarehouseDockUpdatePayload,
  WarehouseMapOut,
  WarehouseSensorRig,
  WarehouseSensorRigHealth,
} from "../types";

export async function listWarehouseMaps(token?: string | null): Promise<WarehouseMapOut[]> {
  return httpRequest<WarehouseMapOut[]>("/warehouse/maps", { token });
}

export async function createWarehouseMap(
  payload: CreateWarehouseMapPayload,
  token?: string | null,
): Promise<WarehouseMapOut> {
  return httpRequest<WarehouseMapOut>("/warehouse/maps", {
    method: "POST",
    body: payload,
    token,
  });
}

export async function fetchSignedTilesetUrl(
  assetId: number,
  token?: string | null,
): Promise<string | null> {
  const data = await httpRequest<{ url?: string }>(
    `/mapping/assets/${assetId}/signed-url?ttl_seconds=3600&path=tileset.json`,
    { token, skipUnauthorizedRedirect: true },
  );
  return typeof data?.url === "string" && data.url.trim() ? data.url : null;
}

export async function listWarehouseDocks(
  warehouseMapId: number,
  token?: string | null,
): Promise<WarehouseDockStation[]> {
  return httpRequest<WarehouseDockStation[]>(`/warehouse/maps/${warehouseMapId}/docks`, {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function createWarehouseDock(
  warehouseMapId: number,
  payload: WarehouseDockPayload,
  token?: string | null,
): Promise<WarehouseDockStation> {
  return httpRequest<WarehouseDockStation>(`/warehouse/maps/${warehouseMapId}/docks`, {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function updateWarehouseDock(
  warehouseMapId: number,
  dockId: number,
  payload: WarehouseDockUpdatePayload,
  token?: string | null,
): Promise<WarehouseDockStation> {
  return httpRequest<WarehouseDockStation>(
    `/warehouse/maps/${warehouseMapId}/docks/${dockId}`,
    {
      method: "PUT",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function deleteWarehouseDock(
  warehouseMapId: number,
  dockId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>(`/warehouse/maps/${warehouseMapId}/docks/${dockId}`, {
    method: "DELETE",
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function listWarehouseSensorRigs(
  token?: string | null,
): Promise<WarehouseSensorRig[]> {
  return httpRequest<WarehouseSensorRig[]>("/warehouse/sensor-rigs", {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function createWarehouseSensorRig(
  payload: CreateWarehouseSensorRigPayload,
  token?: string | null,
): Promise<WarehouseSensorRig> {
  return httpRequest<WarehouseSensorRig>("/warehouse/sensor-rigs", {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function updateWarehouseSensorRigCalibration(
  sensorRigId: number,
  payload: UpdateWarehouseSensorRigCalibrationPayload,
  token?: string | null,
): Promise<WarehouseSensorRig> {
  return httpRequest<WarehouseSensorRig>(
    `/warehouse/sensor-rigs/${sensorRigId}/calibration`,
    {
      method: "POST",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function fetchWarehouseSensorRigHealth(
  sensorRigId: number,
  token?: string | null,
): Promise<WarehouseSensorRigHealth> {
  return httpRequest<WarehouseSensorRigHealth>(
    `/warehouse/sensor-rigs/${sensorRigId}/health`,
    {
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}
