import type { AgricultureCapabilityReadiness } from "../flights/types";

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

export type AgricultureAnalysisReadiness = {
  catalog_version: string;
  flight_id: string;
  mission_id: string;
  ready: boolean;
  media_count: number;
  sensor_inventory: string[];
  capture_prerequisites: Array<{
    id: string;
    label: string;
    satisfied: boolean;
    message: string;
  }>;
  capabilities: AgricultureCapabilityReadiness[];
};

export type AgricultureAnalysisQuality = {
  run_id: string;
  status: string;
  score: number;
  summary: Record<string, unknown>;
  stages: Array<Record<string, unknown>>;
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
  comparability?: Comparability;
};

export type Comparability = {
  eligible: boolean;
  status: string;
  score: number;
  policy_version?: string;
  warnings?: string[];
  blockers?: string[];
  factors?: Record<string, unknown>;
};

export type RankedFinding = {
  rank: number;
  finding_id: string;
  observation_id: string;
  observation_type: string | null;
  geometry_geojson: Record<string, unknown>;
  severity: number;
  confidence: number;
  area_m2: number | null;
  georef_status: string | null;
  review_state: string | null;
  evidence_ids: unknown[];
  model_version: string | null;
  provenance: Record<string, unknown>;
  assigned_to_user_id: number | null;
  merged_into_id: string | null;
  member_observation_ids: unknown[];
  score: number;
  display_status: "shown" | "labeled_low_confidence" | "withheld";
  policy_version: string;
  factors: Record<string, unknown>;
  withhold_reasons: string[];
  limitations: string[];
};

export type RankedFindingPage = {
  schema_version: "agriculture.v1";
  policy_version: string;
  run_id: string;
  limit: number;
  total_candidates: number;
  items: RankedFinding[];
  hotspots: { type?: string; features?: Array<Record<string, unknown>> };
};

export type FieldOutcome = {
  id: string;
  org_id: number | null;
  field_id: number;
  flight_id: string;
  run_id: string;
  observation_id: string;
  outcome_status: string;
  notes: string | null;
  model_version: string | null;
  capability_release_id: string | null;
  created_by_user_id: number | null;
  created_at: string;
};

export type ComparableFlight = {
  flight_id: string;
  created_at: string | null;
  status: string | null;
  comparability: Comparability;
  alignment: Record<string, unknown>;
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
