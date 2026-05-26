export type GridParams = {
  row_spacing_m: number;
  grid_angle_deg: number | null;
  slope_aware?: boolean;
  safety_inset_m: number;
  terrain_follow?: boolean;
  agl_m?: number;
  pattern_mode: "boustrophedon" | "crosshatch";
  crosshatch_angle_offset_deg: number;
  start_corner: "auto" | "nw" | "ne" | "sw" | "se";
  lane_strategy: "serpentine" | "one_way";
  row_stride: number;
  row_phase_m: number;
};

export type GridPreviewWaypoint = { lat: number; lon: number };

export type GridPreviewStats = {
  rows?: number;
  waypoints?: number;
  route_m?: number;
  area_m2?: number;
  passes?: number;
  start_corner?: string;
  lane_strategy?: string;
  row_stride?: number;
  row_phase_m?: number;
};

export type GridPreviewResult = {
  waypoints: GridPreviewWaypoint[];
  work_leg_mask?: boolean[];
  stats?: GridPreviewStats | null;
};

export type PatrolPreviewResult = {
  waypoints: GridPreviewWaypoint[];
  work_leg_mask?: boolean[];
  stats?: GridPreviewStats | null;
};
