import type { GridParams } from "./types";

const BASE_DEFAULT_GRID_PARAMS: GridParams = {
  row_spacing_m: 7.5,
  grid_angle_deg: null,
  slope_aware: false,
  safety_inset_m: 1.5,
  terrain_follow: false,
  agl_m: 30,
  pattern_mode: "boustrophedon",
  crosshatch_angle_offset_deg: 90,
  start_corner: "auto",
  lane_strategy: "serpentine",
  row_stride: 1,
  row_phase_m: 0,
};

export function createDefaultGridParams(
  overrides: Partial<GridParams> = {},
): GridParams {
  return { ...BASE_DEFAULT_GRID_PARAMS, ...overrides };
}
