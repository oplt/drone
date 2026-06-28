import { httpRequest } from "../../../shared/api/httpClient";

export async function runFloorPlaneRansac(
  warehouseMapId: number,
  points_xyz: number[][],
  token?: string | null,
  distance_threshold_m = 0.05,
) {
  return httpRequest<Record<string, unknown>>(
    `/warehouse/maps/${warehouseMapId}/coordinate-setup/floor-plane-ransac`,
    {
      method: "POST",
      body: { points_xyz, distance_threshold_m },
      token,
    },
  );
}

export async function estimateScanOdomAlignment(
  warehouseMapId: number,
  payload: {
    floor_plane: Record<string, unknown>;
    origin_warehouse_m?: number[];
    yaw_flip_rad?: number;
  },
  token?: string | null,
) {
  return httpRequest<Record<string, unknown>>(
    `/warehouse/maps/${warehouseMapId}/coordinate-setup/scan-odom-alignment`,
    { method: "POST", body: payload, token },
  );
}
