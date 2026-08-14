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
  provenance: Record<string, unknown>;
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
  merged_into_id?: string | null;
  split_from_id?: string | null;
  member_observation_ids?: unknown[];
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
    content_type: string | null;
    checksum: string;
    signed_url: string;
    frame_index: number | null;
    timestamp_seconds: number | null;
    timestamp_source: string | null;
    source_video_id: string | null;
  }>;
  geometry: Record<string, unknown>;
  georef_status: string;
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
