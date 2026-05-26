import { httpRequest } from "../../../shared/api/httpClient";
import type { GridParams, GridPreviewResult, PatrolPreviewResult } from "../types";
import type { LonLat } from "../../fields/types";

export async function fetchGridPreview(
  payload: {
    field_polygon_lonlat: LonLat[];
    gridParams: GridParams;
  },
  token?: string | null,
  signal?: AbortSignal,
): Promise<GridPreviewResult> {
  const { field_polygon_lonlat, gridParams } = payload;
  return httpRequest<GridPreviewResult>("/tasks/missions/grid-preview", {
    method: "POST",
    body: {
      field_polygon_lonlat,
      row_spacing_m: gridParams.row_spacing_m,
      grid_angle_deg: gridParams.grid_angle_deg,
      safety_inset_m: gridParams.safety_inset_m,
      pattern_mode: gridParams.pattern_mode,
      crosshatch_angle_offset_deg: gridParams.crosshatch_angle_offset_deg,
      start_corner: gridParams.start_corner,
      lane_strategy: gridParams.lane_strategy,
      row_stride: gridParams.row_stride,
      row_phase_m: gridParams.row_phase_m,
    },
    token,
    signal,
  });
}

export async function fetchPatrolPreview(
  body: Record<string, unknown>,
  token?: string | null,
  signal?: AbortSignal,
): Promise<PatrolPreviewResult> {
  return httpRequest<PatrolPreviewResult>("/tasks/missions/private-patrol/preview", {
    method: "POST",
    body,
    token,
    signal,
  });
}
