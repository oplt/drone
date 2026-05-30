import type {
  MissionCreateResponse,
  PreflightRunResponse,
} from "../../mission-runtime";

export type WarehouseScanStartRequest = {
  warehouse_map_id: number;
  mission_name?: string;
  cruise_alt?: number;
  reference_mapping_job_id?: number | null;
  sensor_rig_id?: number | null;
  dock_id?: number | null;
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

export type WarehouseExplorationProfile = {
  max_radius_m: number;
  min_clearance_m: number;
  max_frontier_candidates: number;
  return_battery_reserve_pct: number;
  max_duration_s: number;
};

export type WarehouseExplorationStartRequest = {
  warehouse_map_id: number;
  mission_name?: string;
  hover_alt_m?: number;
  dock_id?: number | null;
  exploration: {
    max_mission_time_s: number;
    max_exploration_radius_m: number;
    minimum_corridor_clearance_m: number;
    obstacle_clearance_m: number;
    max_frontier_candidates: number;
    battery_return_reserve_pct: number;
  };
};

export type WarehouseManualMappingStartRequest = {
  flight_id: string;
  warehouse_map_id: number;
  sensor_rig_id?: number | null;
  dock_id?: number | null;
};

export type WarehouseManualMappingCommandResponse = {
  accepted: boolean;
  status: string;
  detail?: string | null;
  data?: Record<string, unknown>;
  mapping_job?: {
    job_id?: number;
    warehouse_map_id?: number;
    status?: string;
    error?: string;
  };
};

export type WarehouseMissionLaunchResponse = {
  warehouse_map_id: number;
  warehouse_name: string;
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
  warehouse_map_id: number;
  warehouse_name: string;
  status: string;
  progress?: number;
  error?: string | null;
  source?: "simulation" | "real_flight" | string;
  created_at: string;
  finished_at?: string | null;
  polygon_local_m: Array<[number, number] | number[]>;
  assets: WarehouseScannedMapAssetResponse[];
};

export type WarehouseScannedMapQualityResponse = {
  job_id: number;
  quality_score?: number | null;
  coverage_percent?: number | null;
  drift_estimate_m?: number | null;
  source: string;
  report: Record<string, unknown>;
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
