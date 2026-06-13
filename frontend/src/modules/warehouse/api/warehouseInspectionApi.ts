import { httpRequest } from "../../../shared/api/httpClient";

export type WarehouseLocalPoint = {
  frame_id?: string;
  x_m: number;
  y_m: number;
  z_m: number;
};

export type WarehouseLocalPose = WarehouseLocalPoint & {
  yaw_deg?: number | null;
};

export type WarehouseShelfNormal = {
  frame_id?: string;
  x: number;
  y: number;
  z?: number;
};

export type WarehouseScanTarget = {
  id: number;
  warehouse_map_id: number;
  reference_model_id: number | null;
  dock_station_id: number | null;
  aisle_code: string;
  rack_code: string | null;
  shelf_level: number | null;
  bin_code: string | null;
  sku: string | null;
  barcode: string | null;
  product_name: string | null;
  target_point_local_json: WarehouseLocalPoint;
  scan_pose_local_json: WarehouseLocalPose;
  shelf_normal_local_json: WarehouseShelfNormal | null;
  standoff_m: number;
  hover_time_s: number;
  scan_timeout_s: number;
  priority: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type WarehouseScanTargetPayload = {
  aisle_code: string;
  rack_code?: string | null;
  shelf_level?: number | null;
  bin_code?: string | null;
  sku?: string | null;
  barcode?: string | null;
  product_name?: string | null;
  target_point_local_json: WarehouseLocalPoint;
  scan_pose_local_json: WarehouseLocalPose;
  shelf_normal_local_json?: WarehouseShelfNormal | null;
  standoff_m?: number;
  hover_time_s?: number;
  scan_timeout_s?: number;
  priority?: number;
  active?: boolean;
};

export type WarehouseInspectionMission = {
  id: number;
  warehouse_map_id: number;
  name: string;
  status: string;
  scan_mode: "barcode" | "product_photo" | "visual_check" | "mixed" | string;
  return_to_dock: boolean;
  target_ids: number[];
  waypoints: Array<{
    target_id: number;
    purpose: string;
    pose: WarehouseLocalPose;
    hover_time_s: number;
    scan_timeout_s: number;
    metadata: Record<string, unknown>;
  }>;
  created_at: string;
  updated_at: string;
};

export type WarehouseInspectionResult = {
  id: number;
  mission_id: number;
  target_id: number;
  status: string;
  expected_barcode: string | null;
  detected_barcode: string | null;
  confidence: number | null;
  image_asset_id: number | null;
  video_asset_id: number | null;
  drone_pose_local_json: WarehouseLocalPose | null;
  error_message: string | null;
  scanned_at: string;
};

export async function computeWarehouseScanPose(
  payload: {
    target_point: WarehouseLocalPoint;
    shelf_normal?: WarehouseShelfNormal | null;
    standoff_m?: number;
    yaw_deg?: number | null;
  },
  token?: string | null,
): Promise<{ scan_pose: WarehouseLocalPose }> {
  return httpRequest<{ scan_pose: WarehouseLocalPose }>(
    "/warehouse/scan-targets/compute-scan-pose",
    { method: "POST", body: payload, token, skipUnauthorizedRedirect: true },
  );
}

export async function listWarehouseScanTargets(
  warehouseMapId: number,
  token?: string | null,
): Promise<WarehouseScanTarget[]> {
  return httpRequest<WarehouseScanTarget[]>(
    `/warehouse/maps/${warehouseMapId}/scan-targets`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export async function createWarehouseScanTarget(
  warehouseMapId: number,
  payload: WarehouseScanTargetPayload,
  token?: string | null,
): Promise<WarehouseScanTarget> {
  return httpRequest<WarehouseScanTarget>(
    `/warehouse/maps/${warehouseMapId}/scan-targets`,
    { method: "POST", body: payload, token, skipUnauthorizedRedirect: true },
  );
}

export async function updateWarehouseScanTarget(
  warehouseMapId: number,
  targetId: number,
  payload: Partial<WarehouseScanTargetPayload>,
  token?: string | null,
): Promise<WarehouseScanTarget> {
  return httpRequest<WarehouseScanTarget>(
    `/warehouse/maps/${warehouseMapId}/scan-targets/${targetId}`,
    { method: "PATCH", body: payload, token, skipUnauthorizedRedirect: true },
  );
}

export async function deleteWarehouseScanTarget(
  warehouseMapId: number,
  targetId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>(
    `/warehouse/maps/${warehouseMapId}/scan-targets/${targetId}`,
    { method: "DELETE", token, skipUnauthorizedRedirect: true },
  );
}

export async function createWarehouseInspectionMission(
  payload: {
    warehouse_map_id: number;
    name: string;
    target_ids: number[];
    scan_mode: "barcode" | "product_photo" | "visual_check" | "mixed";
    optimize_order: boolean;
    return_to_dock: boolean;
  },
  token?: string | null,
): Promise<WarehouseInspectionMission> {
  return httpRequest<WarehouseInspectionMission>("/warehouse/inspection-missions", {
    method: "POST",
    body: payload,
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function runWarehouseInspectionMissionMock(
  missionId: number,
  token?: string | null,
): Promise<WarehouseInspectionResult[]> {
  return httpRequest<WarehouseInspectionResult[]>(
    `/warehouse/inspection-missions/${missionId}/run-mock`,
    { method: "POST", token, skipUnauthorizedRedirect: true },
  );
}

export async function listWarehouseInspectionResults(
  missionId: number,
  token?: string | null,
): Promise<WarehouseInspectionResult[]> {
  return httpRequest<WarehouseInspectionResult[]>(
    `/warehouse/inspection-missions/${missionId}/results`,
    { token, skipUnauthorizedRedirect: true },
  );
}
