import { httpRequest } from "../../../shared/api/httpClient";
import type {
  CreateWarehouseMapPayload,
  CreateWarehouseSensorRigPayload,
  UpdateWarehouseSensorRigCalibrationPayload,
  WarehouseDockPayload,
  WarehouseDockStation,
  WarehouseDockUpdatePayload,
  WarehouseMapOut,
  WarehouseMapSetup,
  WarehouseMapSetupPreview,
  WarehouseRigidTransform,
  WarehouseSensorRig,
  WarehouseSensorRigHealth,
} from "../types";

export async function listWarehouseMaps(token?: string | null): Promise<WarehouseMapOut[]> {
  return httpRequest<WarehouseMapOut[]>("/warehouse/maps", { token });
}

export async function createWarehouseMapSetup(
  warehouseMapId: number,
  payload: {
    polygon_local_m: [number, number][];
    origin_transform: WarehouseRigidTransform;
    alignment_deg: number;
    alignment_reference: "north" | "aisle";
    source: string;
    confidence: number;
    transform_timestamp: string;
    max_transform_age_s: number;
    covariance: number[];
    localization_method: string;
    map_resolution_m?: number | null;
    scale: 1;
    known_distance_expected_m?: number | null;
    known_distance_measured_m?: number | null;
  },
  token?: string | null,
): Promise<WarehouseMapSetup> {
  return httpRequest(`/warehouse/maps/${warehouseMapId}/setups`, {
    method: "POST", body: payload, token,
  });
}

export async function previewWarehouseMapSetup(
  warehouseMapId: number, setupId: number, token?: string | null,
): Promise<WarehouseMapSetupPreview> {
  return httpRequest(`/warehouse/maps/${warehouseMapId}/setups/${setupId}/preview`, { token });
}

export async function lockWarehouseMapSetup(
  warehouseMapId: number, setupId: number, token?: string | null,
): Promise<WarehouseMapSetup> {
  return httpRequest(`/warehouse/maps/${warehouseMapId}/setups/${setupId}/lock`, {
    method: "POST", token,
  });
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

export async function deleteWarehouseMap(
  warehouseMapId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>(`/warehouse/maps/${warehouseMapId}`, {
    method: "DELETE",
    token,
    skipUnauthorizedRedirect: true,
  });
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

export async function deleteWarehouseSensorRig(
  sensorRigId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>(`/warehouse/sensor-rigs/${sensorRigId}`, {
    method: "DELETE",
    token,
    skipUnauthorizedRedirect: true,
  });
}
