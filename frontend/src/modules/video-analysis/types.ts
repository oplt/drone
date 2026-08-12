export type VideoAsset = {
  id: string;
  mission_id?: string | null;
  field_id?: number | null;
  original_filename: string;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  duration_seconds?: number | null;
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
  model_name: string;
  model_version_id?: string | null;
  model_version?: string;
  small_object_mode?: boolean;
  tracking_enabled?: boolean;
  tracker_type?: "bytetrack";
  frame_stride_seconds: number;
  confidence_threshold: number;
  started_at?: string | null;
  finished_at?: string | null;
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
  evidence_path?: string | null;
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
