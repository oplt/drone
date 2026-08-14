export type AgricultureSensorType = "rgb" | "multispectral" | "thermal" | "stereo" | "lidar";

export type AgricultureMissionProfile = {
  flight_kind: "agriculture_survey";
  preset:
    | "early_stand_count"
    | "rgb_weed_water"
    | "repeat_monitoring"
    | "multispectral_thermal";
  crop_type: string;
  variety: string;
  season: string;
  growth_stage: string;
  row_direction_deg: number | null;
  expected_row_spacing_m: number | null;
  expected_plant_spacing_m?: number | null;
  stand_gap_multiplier?: number;
  weed_density_cell_m?: number;
  weed_hotspot_percentile?: number;
  target_gsd_cm: number;
  speed_mps: number;
  front_overlap_pct: number;
  side_overlap_pct: number;
  camera_orientation: "nadir" | "oblique";
  fov_h_deg: number;
  fov_v_deg: number;
  camera_resolution_width_px: number;
  camera_resolution_height_px: number;
  focal_length_mm: number | null;
  grid_angle_deg: number | null;
  sensor_inventory: AgricultureSensorType[];
  calibration_ids: string[];
  requested_analyses: string[];
  repeat_interval_days: number | null;
  plan_id?: string | null;
  preflight_snapshot_id?: string | null;
};

export type AgriculturePlanRequest = {
  field_id: number;
  field_polygon_lonlat: number[][];
  cruise_alt_m: number;
  row_spacing_m: number;
  grid_angle_deg: number;
  safety_inset_m: number;
  pattern_mode: "boustrophedon" | "crosshatch";
  crosshatch_angle_offset_deg: number;
  lane_strategy: "serpentine" | "one_way";
  start_corner: "auto" | "nw" | "ne" | "sw" | "se";
  row_stride: number;
  row_phase_m: number;
  max_waypoints_per_segment?: number;
  exclusion_zones?: Array<Record<string, unknown>>;
  obstacle_zones?: Array<Record<string, unknown>>;
  takeoff_point_lonlat?: number[] | null;
  landing_point_lonlat?: number[] | null;
  profile: AgricultureMissionProfile;
};

export type AgriculturePlan = {
  id: string;
  field_id: number;
  status: "draft" | "validated" | "committed" | "superseded" | "invalid" | string;
  plan_hash: string;
  payload: Record<string, unknown>;
  route_geojson: Record<string, unknown>;
  estimates: Record<string, unknown>;
  warnings: string[];
  validation_errors: string[];
  created_at: string;
  grid_revision: number;
  planner_version: string;
};

export type AgriculturePreflightCheck = {
  code: string;
  label: string;
  status: "PASS" | "BLOCK" | "WARN" | string;
  blocking: boolean;
  observed?: unknown;
  source?: string;
  message?: string;
  remediation?: string;
  evaluated_at?: string;
};

export type AgriculturePreflightSnapshot = {
  id: string;
  plan_id: string;
  status: "blocked" | "warning" | "pass" | "expired" | string;
  checks: AgriculturePreflightCheck[];
  acknowledged: boolean;
  expires_at: string;
  evaluated_at?: string | null;
  evaluator_version?: string;
  signoff_hash?: string | null;
  operator_notes?: string | null;
};

export type AgricultureMediaInventory = {
  flight_id: string;
  status: string;
  registered: number;
  expected: number;
  missing_manifest_ids: string[];
  ready_for_processing: boolean;
  storage_missing_media_ids: string[];
  quarantined_media_ids: string[];
  active_upload_ids: string[];
  quarantined_upload_ids: string[];
  processed_frame_count: number;
  open_exception_count: number;
  storage_usage_bytes: number;
  storage_quota_bytes: number;
  manifests: AgricultureMediaArtifact[];
  uploads: Array<Record<string, unknown>>;
  exceptions: Array<Record<string, unknown>>;
};

export type AgricultureMediaArtifact = {
  id: string;
  source_kind: string;
  checksum: string;
  content_type?: string | null;
  byte_size?: number | null;
  retention_status: string;
  storage_class: string;
  artifact_version: number;
  retention_expires_at?: string | null;
  revoked_at?: string | null;
  security_status: string;
  security_reason?: string | null;
  security_checked_at?: string | null;
  storage_present: boolean;
};

export type AgricultureMediaTimeline = {
  flight_id: string;
  total: number;
  truncated: boolean;
  frames: Array<{
    id: string;
    frame_index: number;
    timestamp_utc: string;
    media_id: string | null;
    signed_url: string | null;
    content_type: string | null;
    footprint_geojson: Record<string, unknown>;
    gsd_cm: number | null;
    quality_metrics: Record<string, unknown>;
    telemetry_sample_before_id: number | null;
    telemetry_sample_after_id: number | null;
  }>;
};

export type AgricultureTelemetryWindow = {
  flight_id: string;
  center_timestamp_utc: string | null;
  window_seconds: number;
  truncated: boolean;
  samples: Array<{
    id: number;
    timestamp_utc: string;
    lat: number;
    lon: number;
    relative_altitude_m: number | null;
    absolute_altitude_m: number | null;
    ground_speed_mps: number | null;
    gps_quality: number | null;
    yaw_deg: number | null;
    camera_trigger: boolean | null;
    source: string;
  }>;
};

export type AgricultureTimelineBookmark = { id: string; flight_id?: string; frame_lineage_id: string; note: string | null; created_at: string; updated_at: string };

export type AgricultureSensorCalibration = {
  id: string;
  sensor_serial: string;
  sensor_type: string;
  version: string;
  calibration_kind: string;
  checksum: string;
  valid_from?: string | null;
  valid_until?: string | null;
};

export type AgricultureModelVersion = {
  id: string;
  task: string;
  version: string;
  status: "candidate" | "validated" | "deployed" | "retired" | string;
  artifact_uri: string | null;
  dataset_key: string | null;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  deployed_at: string | null;
  created_at: string;
};

export type AgricultureModelReleaseGate = {
  model_id: string;
  task: string;
  version: string;
  status: string;
  report_id: string | null;
  evaluation_checksum: string | null;
  metric_gate: Record<string, unknown>;
  evidence_gate: { publishable: boolean; failures: string[]; scope: Record<string, unknown>; artifact_digest?: string | null };
  publishable: boolean;
};

export type AgricultureFlight = {
  id: string;
  mission_id: string;
  field_id: number;
  org_id: number | null;
  season: string | null;
  flight_kind: string;
  status: string;
  profile_snapshot: Record<string, unknown>;
  profile_snapshot_version: number;
  profile_snapshot_hash: string | null;
  quality_summary: Record<string, unknown>;
  coverage_summary: Record<string, unknown>;
  input_manifest: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
};

export type AgricultureCapabilityReadiness = {
  id: string;
  label: string;
  description: string;
  available: boolean;
  recommended: boolean;
  unavailable_reasons: string[];
  required_sensor: string;
  required_media: string;
  requires_model: boolean;
  output_type: string;
  action_relevance: string;
  crop_specific?: boolean;
  capture_conditions?: Record<string, unknown>;
  evaluation_thresholds?: Record<string, number>;
  limitations?: string[];
  advanced_defaults: Record<string, unknown>;
  release: Record<string, unknown> | null;
};

export type AgricultureUploadSession = {
  id: string;
  status: "uploading" | "completed" | "expired" | "quarantined";
  upload_offset: number;
  total_bytes: number;
  chunk_bytes: number;
  chunk_url: string;
  complete_url: string;
  expires_at: string;
};

export type AgricultureTimelineFlight = Pick<
  AgricultureFlight,
  "id" | "created_at" | "status" | "quality_summary" | "coverage_summary"
>;

export type AgricultureSensorStatus = {
  flight_id: string;
  inventory: string[];
  spectral: Record<string, unknown>;
  calibration_ids: string[];
  profile_calibration_ids?: string[];
  calibration_status?: string;
  calibrations?: Array<{ id: string; sensor_serial: string; sensor_type: string; version: string; checksum: string; valid: boolean; valid_from?: string | null; valid_until?: string | null }>;
  readings: Record<
    string,
    {
      status: string;
      age_seconds?: number;
      stale_after_seconds?: number;
      quality?: number;
      source?: string;
      timestamp?: string;
      values?: Record<string, unknown>;
      units?: Record<string, unknown>;
    }
  >;
  status: string;
};
