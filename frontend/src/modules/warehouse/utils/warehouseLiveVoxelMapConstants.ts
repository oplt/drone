export type WarehouseLiveVoxelConnectionState =
  | "empty"
  | "connecting"
  | "live"
  | "stale"
  | "reconnecting"
  | "finalized"
  | "failed";

export const WAREHOUSE_LIVE_VOXEL_STALE_AFTER_MS = 10_000;

export const WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH = {
  coverage_percent: null,
  drift_estimate_m: null,
  stale_costmap: false,
  missing_mesh: true,
  missing_point_cloud: true,
  nvblox_ready: false,
  mapping_recording: false,
  stack_running: false,
} as const;
