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
export type AgricultureReport = {
  run_id: string;
  flight_id: string;
  status: string;
  progress: number;
  quality_gate: Record<string, unknown>;
  counters: Record<string, unknown>;
  model_versions: Record<string, unknown>;
  calibration_versions: Record<string, unknown>;
  summary: { observation_count: number; by_type: Record<string, number>; by_review_state: Record<string, number>; confirmed_count: number; unreviewed_count: number; layer_names: string[] };
  limitations: string[];
};
export type AgricultureReportSnapshot = {
  id: string;
  field_id: number;
  flight_id: string;
  run_id: string;
  template_key: string;
  template_version: string;
  snapshot_json: Record<string, unknown>;
  checksum: string;
  created_by_user_id: number | null;
  created_at: string;
};
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

export type AgricultureFieldProfile = {
  id: number;
  field_id: number;
  crop_type: string | null;
  variety: string | null;
  season: string | null;
  planting_date: string | null;
  growth_stage: string | null;
  row_direction_deg: number | null;
  expected_row_spacing_m: number | null;
  soil_type: string | null;
  irrigation_method: string | null;
  management_zone: string | null;
  timezone: string;
  notes: string | null;
  metadata: Record<string, unknown>;
};

export type AgricultureFieldZone = {
  id: string;
  zone_type: "exclusion" | "obstacle";
  geometry: Record<string, unknown>;
  name: string;
  kind: string;
  radius_m: number | null;
  height_m: number | null;
  metadata: Record<string, unknown>;
  revision: number;
  created_at: string;
};

export type AgricultureBoundaryRevision = {
  revision: number;
  boundary: Record<string, unknown>;
  area_ha: number;
  created_at: string;
};

export type AgricultureFieldContext = {
  field_id: number;
  name: string;
  area_ha: number | null;
  boundary: { type: "Polygon"; coordinates: number[][][] };
  current_revision: number;
  revisions: AgricultureBoundaryRevision[];
  zones: AgricultureFieldZone[];
};

export type AgriculturePlanPreview = {
  field_id: number | null;
  area_m2: number;
  area_ha: number;
  footprint_width_m: number;
  footprint_height_m: number;
  estimated_gsd_cm: number;
  coverage_pct: number;
  estimated_duration_s: number | null;
  estimated_image_count: number | null;
  warnings: string[];
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
export type AgricultureFieldOverview = {
  id: number;
  name: string;
  area_ha: number | null;
  workflow_scope: string | null;
  geometry_geojson: Record<string, unknown>;
  profile: {
    crop_type?: string | null;
    variety?: string | null;
    season?: string | null;
    growth_stage?: string | null;
  };
  latest_flight: {
    id: string;
    status: string;
    created_at: string;
    quality_summary: Record<string, unknown>;
    coverage_summary: Record<string, unknown>;
  } | null;
};

export type AgricultureAnalysisRun = {
  id: string;
  flight_id: string;
  status: string;
  requested_analyses: unknown[];
  analysis_profile: Record<string, unknown>;
  input_manifest: Record<string, unknown>;
  input_checksum: string | null;
  model_versions: Record<string, unknown>;
  calibration_versions: Record<string, unknown>;
  parameters: Record<string, unknown>;
  baseline_flight_id: string | null;
  retry_count: number;
  audit_json: Record<string, unknown>;
  requested_by_user_id: number | null;
  progress: number;
  error?: string | null;
  quality_gate: Record<string, unknown>;
  counters: Record<string, unknown>;
  created_at: string;
};
export type AgricultureAnalysisQuality = {
  run_id: string;
  status: string;
  score: number;
  summary: Record<string, unknown>;
  stages: Array<Record<string, unknown>>;
};
export type AgricultureObservation = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  observation_type: string;
  zone_kind: "observation" | "management_zone" | "prescription_zone";
  geometry_geojson: Record<string, unknown>;
  georef_status: string;
  area_m2: number | null;
  severity: number;
  confidence: number;
  uncertainty: Record<string, unknown>;
  first_detected: string | null;
  last_detected: string | null;
  trend: string;
  evidence_ids: string[];
  sensor_values: Record<string, unknown>;
  model_version: string | null;
  review_state: string;
  review_label: string | null;
  review_note: string | null;
  assigned_to_user_id?: number | null;
  review_due_at?: string | null;
  reviewed_at: string | null;
};
export type AgricultureObservationPage = {
  schema_version: "agriculture.v1";
  items: AgricultureObservation[];
  next_cursor: string | null;
  total: number;
};
export type AgricultureObservationFeedback = {
  id: string;
  observation_id: string;
  actor_user_id: number | null;
  feedback_type: "correction" | "disagreement" | "comment";
  proposed_label: string | null;
  proposed_severity: number | null;
  proposed_zone_kind: AgricultureObservation["zone_kind"] | null;
  proposed_geometry_geojson: Record<string, unknown>;
  comment: string;
  evidence_ids: string[];
  status: "submitted" | "accepted" | "rejected";
  decision_note: string | null;
  annotation_id: string | null;
  decided_at: string | null;
  created_at: string;
};
export type AgricultureObservationEvidence = {
  observation_id: string;
  evidence_ids: string[];
  assets: Array<{
    evidence_id: string;
    media_id: string;
    source_kind: string;
    checksum: string;
    signed_url: string;
  }>;
  geometry: Record<string, unknown>;
  georef_status: string;
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
export type AgricultureLayer = {
  run_id: string;
  layer: string;
  status: string;
  geojson: { type?: string; features?: Array<Record<string, unknown>> };
  summary: Record<string, unknown>;
  checksum: string;
};
export type AgricultureSpatialViewport = {
  schema_version: "agriculture.v1";
  run_id: string;
  layer: string;
  zoom: number;
  bbox: number[] | null;
  total: number;
  returned: number;
  partial: boolean;
  aggregation: "grid-cluster" | "raw";
  geojson: { type?: string; features?: Array<Record<string, unknown>> };
  quality: { status: string; source: string };
};
export type AgricultureSpatialLayers = {
  run_id: string;
  layers: Array<{ layer: string; status: string; summary: Record<string, unknown>; checksum: string; generated_at: string }>;
  quality_gate: Record<string, unknown>;
};
export type AgricultureChange = {
  id: string;
  field_id: number;
  current_flight_id: string;
  reference_flight_id: string;
  current_observation_id: string | null;
  previous_observation_id: string | null;
  observation_type: string;
  state: "new" | "expanding" | "stable" | "improving" | "resolved";
  geometry_geojson: Record<string, unknown>;
  reference_geometry_geojson: Record<string, unknown>;
  area_m2: number | null;
  delta_area_m2: number | null;
  delta_intensity: number | null;
  confidence: number;
  evidence_ids: string[];
  uncertainty: Record<string, unknown>;
  created_at: string;
};
export type AgricultureComparison = {
  id: string | null;
  status: string;
  current_flight_id: string;
  reference_flight_id: string | null;
  alignment: Record<string, unknown>;
  summary: Record<string, number>;
  changes: AgricultureChange[];
};
export type AgricultureAnnotation = {
  id: string;
  observation_id: string;
  version: number;
  status: "draft" | "submitted" | "approved" | "rejected";
  label: string;
  severity: number;
  geometry_geojson: Record<string, unknown>;
  evidence_ids: string[];
  notes: string | null;
  created_by_user_id: number | null;
  approved_by_user_id: number | null;
  created_at: string;
  updated_at: string;
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
export type AgricultureFusionResult = {
  layer: string;
  status: string;
  measured: boolean;
  units: string | null;
  summary: Record<string, unknown>;
  required_inputs: unknown[];
  source_ids: unknown[];
  source_timestamps: unknown[];
  confidence: number;
  uncertainty: Record<string, unknown>;
  evidence: unknown[];
  failure_reasons: unknown[];
  model_version: string | null;
};
export type AgricultureCropRisk = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  issue_type: string;
  status: string;
  crop_type: string | null;
  growth_stage: string | null;
  geometry_geojson: Record<string, unknown>;
  severity: number;
  confidence: number;
  trend: string;
  uncertainty: Record<string, unknown>;
  evidence_ids: unknown[];
  sensor_values: Record<string, unknown>;
  inspection_points: unknown[];
  factors: Record<string, unknown>;
  applicability: Record<string, unknown>;
  model_version: string | null;
  review_state: string;
  review_note: string | null;
  reviewed_at: string | null;
};
export type AgricultureGrowthMetric = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  metric_kind: string;
  status: string;
  units: string | null;
  summary: Record<string, unknown>;
  source_ids: unknown[];
  source_timestamps: unknown[];
  confidence: number;
  uncertainty: Record<string, unknown>;
  evidence_ids: unknown[];
  model_version: string | null;
};
export type AgricultureGrowthStage = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  status: string;
  predicted_stage: string | null;
  candidates: unknown[];
  confidence: number;
  inputs: Record<string, unknown>;
  evidence_ids: unknown[];
  uncertainty: Record<string, unknown>;
  human_stage: string | null;
  correction_note: string | null;
  corrected_at: string | null;
  model_version: string | null;
};
export type AgricultureYieldForecast = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  status: string;
  units: string | null;
  forecast_range: Record<string, unknown>;
  confidence_interval: Record<string, unknown>;
  confidence: number;
  factors: Record<string, unknown>;
  applicability: Record<string, unknown>;
  evidence_ids: unknown[];
  harvest_label_ids: unknown[];
  uncertainty: Record<string, unknown>;
  model_version: string | null;
};
export type AgricultureInspectionAction = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  source_ids: unknown[];
  priority_rank: number;
  priority_score: number;
  severity: number;
  confidence: number;
  area_m2: number | null;
  issue_type: string;
  geometry_geojson: Record<string, unknown>;
  waypoint_geojson: Record<string, unknown>;
  rationale: string;
  route_constraints: Record<string, unknown>;
  uncertainty: Record<string, unknown>;
  status: string;
  review_note: string | null;
  reviewed_at: string | null;
  assigned_to_user_id?: number | null;
  due_at?: string | null;
};
export type AgriculturePrescription = {
  id: string;
  run_id: string;
  flight_id: string;
  field_id: number;
  rule_id: string | null;
  status: string;
  zones: unknown[];
  source_ids: unknown[];
  rule_provenance: Record<string, unknown>;
  model_provenance: Record<string, unknown>;
  assumptions: unknown[];
  confidence: number;
  uncertainty: Record<string, unknown>;
  review_note: string | null;
  reviewed_at: string | null;
};
export type AgricultureExport = {
  id: string;
  field_id: number;
  flight_id: string | null;
  run_id: string | null;
  artifact_kind: string;
  format: string;
  status: string;
  checksum: string | null;
  content_type: string | null;
  source_manifest: Record<string, unknown>;
  expires_at: string | null;
  requested_by_user_id: number | null;
  approved_by_user_id: number | null;
  created_at: string;
};
export type AgricultureAssistantRun = {
  id: string;
  run_id: string;
  field_id: number;
  flight_id: string;
  task: string;
  status: string;
  decision_status: string;
  prompt_version: string;
  context_checksum: string;
  source_ids: unknown[];
  deterministic_rules: Array<Record<string, unknown>>;
  output: {
    summary?: string;
    key_points?: string[];
    next_steps?: string[];
    cited_source_ids?: string[];
    limitations?: string[];
    confidence?: number;
    risk_level?: string;
    abstained?: boolean;
    human_approval_required?: boolean;
  };
  citations: Array<Record<string, unknown>>;
  limitations: string[];
  confidence: number;
  risk_level: string;
  requires_human_approval: boolean;
  abstained: boolean;
  profile_id: string | null;
  model: string | null;
  error_code: string | null;
  review_status: string;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
};
