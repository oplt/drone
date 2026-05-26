import type {
  MissionCreateResponse,
  PreflightRunResponse,
} from "../../mission-runtime";

export type WarehouseScanStartRequest = {
  field_id?: number;
  warehouse_map_id?: number;
  mission_name?: string;
  cruise_alt?: number;
  reference_mapping_job_id?: number | null;
  corridor_spacing_m?: number;
  aisle_axis_deg?: number | null;
  clearance_m?: number;
  perimeter_offset_m?: number;
  scan_pattern?: "aisle_serpentine" | "stacked_passes" | "crosshatch" | "perimeter_aisle_hybrid";
  lane_strategy?: "serpentine" | "one_way";
  view_mode?: "forward" | "left_face" | "right_face" | "dual_face";
  layer_count?: number;
  layer_spacing_m?: number;
  ceiling_height_m?: number;
  ceiling_margin_m?: number;
  work_speed_mps?: number;
  transit_speed_mps?: number;
  scan_pause_s?: number;
  interpolate_steps_work_leg?: number;
  interpolate_steps_transit_leg?: number;
};

export type WarehouseMissionLaunchResponse = {
  field_id: number;
  field_name: string;
  preflight: PreflightRunResponse;
  mission: MissionCreateResponse;
};

export type WarehouseScannedMapAssetResponse = {
  id: number;
  type: string;
  url: string;
  created_at: string;
  meta_data?: Record<string, unknown>;
};

export type WarehouseScannedMapResponse = {
  job_id: number;
  model_id: number;
  model_version: number;
  field_id: number;
  field_name: string;
  status: string;
  created_at: string;
  finished_at?: string | null;
  boundary_lonlat: Array<[number, number] | number[]>;
  assets: WarehouseScannedMapAssetResponse[];
};

export type WarehouseMissionDefaultsResponse = {
  cruise_alt: number;
  corridor_spacing_m: number;
  aisle_axis_deg: number | null;
  clearance_m: number;
  perimeter_offset_m: number;
  scan_pattern: "aisle_serpentine" | "stacked_passes" | "crosshatch" | "perimeter_aisle_hybrid";
  lane_strategy: "serpentine" | "one_way";
  view_mode: "forward" | "left_face" | "right_face" | "dual_face";
  layer_count: number;
  layer_spacing_m: number;
  ceiling_height_m: number;
  ceiling_margin_m: number;
  work_speed_mps: number;
  transit_speed_mps: number;
  scan_pause_s: number;
  interpolate_steps_work_leg: number;
  interpolate_steps_transit_leg: number;
};
