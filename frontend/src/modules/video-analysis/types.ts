export type VideoAsset = {
  id: string;
  mission_id?: string | null;
  field_id?: number | null;
  original_filename: string;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  duration_seconds?: number | null;
  captured_at?: string | null;
  capture_time_source?: "container" | "mission" | "operator" | "upload_time" | "unknown";
  capture_timezone?: string | null;
  capture_time_uncertainty_seconds?: number | null;
  sync_offset_seconds?: number;
  status: string;
  created_at: string;
};

export type VideoAnalysisJob = {
  id: string;
  video_id: string;
  mission_id?: string | null;
  status: "queued" | "running" | "completed" | "failed" | string;
  progress: number;
  error?: string | null;
  terminal_reason_code?: string | null;
  terminal_stage?: string | null;
  attempt?: number;
  heartbeat_at?: string | null;
  lease_expires_at?: string | null;
  frames_received?: number;
  frames_decoded?: number;
  frames_attempted?: number;
  frames_processed?: number;
  frames_persisted?: number;
  frames_dropped?: number;
  frames_failed?: number;
  model_name: string;
  model_version_id?: string | null;
  model_version?: string;
  loaded_model_hash?: string | null;
  small_object_mode?: boolean;
  tracking_enabled?: boolean;
  tracker_type?: "bytetrack";
  frame_stride_seconds: number;
  confidence_threshold: number;
  started_at?: string | null;
  finished_at?: string | null;
  stage_timings?: Record<string, number>;
  created_at: string;
};

export type VideoDetection = {
  id: string;
  job_id: string;
  video_id: string;
  mission_id?: string | null;
  frame_index: number;
  timestamp_seconds: number;
  label: string;
  confidence: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  track_id?: number | null;
  lat?: number | null;
  lon?: number | null;
  altitude_m?: number | null;
  heading_deg?: number | null;
  evidence?: {
    type: "detection_crop";
    source_entity_id: string;
    frame_index: number;
    timestamp: number;
    storage_object_id: string;
    checksum: string;
    availability: "available" | "missing" | "deleted";
    spatial?: Record<string, number> | null;
    provenance: Record<string, unknown>;
  } | null;
  evidence_url?: string | null;
  evidence_path?: null;
  telemetry_match_quality?: string | null;
  telemetry_match_delta_ms?: number | null;
  telemetry_match_method?: string | null;
  telemetry_match_version?: string | null;
};

export type VideoDetectionPage = {
  items: VideoDetection[];
  next_cursor: string | null;
  has_more: boolean;
  job_version: number;
  status: string;
  total_estimate?: number | null;
};

export type AnalyzeVideoPayload = {
  model_name: string;
  model_version_id?: string | null;
  small_object_mode?: boolean;
  tracking_enabled?: boolean;
  tracker_type?: "bytetrack";
  frame_stride_seconds: number;
  confidence_threshold: number;
};

export type VideoAnalysisSummary = {
  job_id: string;
  frames_analyzed: number;
  detections_by_class: Record<string, number>;
  unique_tracked_objects_by_class: Record<string, number>;
  confidence_distribution: {
    minimum: number | null;
    mean: number | null;
    maximum: number | null;
  };
  model_name: string;
  model_version: string;
  model_version_id: string | null;
  registered_model: {
    name: string;
    version: number;
    crop: string;
    task_type: string;
    classes: string[];
  } | null;
  tracking_enabled: boolean;
  tracker_type: "bytetrack";
  small_object_mode: boolean;
  frame_stride_seconds: number;
  confidence_threshold: number;
};

export type LiveSavedDetection = {
  id: number;
  flight_id: number;
  created_at: string;
  label: string;
  confidence: number;
  bbox_xyxy: Record<string, number>;
  lat?: number | null;
  lon?: number | null;
  model_name?: string | null;
  meta_data: Record<string, unknown>;
};
