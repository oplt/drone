export type VisionClass = {
  id: string;
  name: string;
  class_index: number;
};

export type VisionProject = {
  id: string;
  name: string;
  description: string | null;
  crop: string;
  capability_id: string;
  task_type: "detection";
  status: string;
  classes: VisionClass[];
  dataset_count: number;
  latest_dataset_status: string | null;
  latest_model_version: number | null;
  production_model_version: number | null;
  created_at: string;
  updated_at: string;
};

export type VisionCurationSummary = {
  policy_version?: string;
  duplicate_cluster_count?: number;
  near_duplicate_clusters?: Array<{
    cluster_id: string;
    size: number;
    image_ids: string[];
  }>;
  near_duplicate_rejected?: number;
  excluded_images?: number;
  quality_exclusions?: number;
  split_leakage_risk?: boolean;
  split_leakage?: {
    held_boundary_frames?: number;
    nearest_cross_split_similarity_count?: number;
  };
  source_distribution?: {
    by_source_group?: Record<string, number>;
    by_split?: Record<string, Record<string, number>>;
  };
  quality_flags?: Record<string, boolean>;
  blur?: Record<string, number | null | undefined>;
  exposure?: Record<string, number | null | undefined>;
};

export type VisionDataset = {
  id: string;
  project_id: string;
  version: number;
  status: string;
  source_count: number;
  image_count: number;
  labeled_count: number;
  reviewed_count: number;
  selected_count: number;
  train_count: number;
  val_count: number;
  test_count: number;
  manifest_checksum: string | null;
  curation_summary?: VisionCurationSummary;
  locked_at: string | null;
  created_at: string;
  updated_at: string;
};

export type VisionAnnotation = {
  id: string;
  class_id: string;
  annotation_type: "bbox";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number | null;
  source: "manual" | "auto" | "imported";
  created_at: string;
  updated_at: string;
};

export type AnnotationInput = Pick<
  VisionAnnotation,
  "class_id" | "x1" | "y1" | "x2" | "y2"
> & {
  id?: string;
  source?: VisionAnnotation["source"];
  confidence?: number | null;
};

export type VisionImage = {
  id: string;
  dataset_id: string;
  content_url: string;
  thumbnail_url: string;
  source_type: string;
  source_video_id: string | null;
  mission_id: string | null;
  field_id: number | null;
  frame_index: number | null;
  timestamp_seconds: number | null;
  width: number;
  height: number;
  quality_score: number | null;
  selected: boolean;
  split: "train" | "val" | "test" | null;
  annotation_status: "unlabeled" | "labeled" | "reviewed";
  annotation_revision: number;
  annotations: VisionAnnotation[];
  lat: number | null;
  lon: number | null;
  altitude_m: number | null;
  heading_deg: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type VisionImagePage = {
  items: VisionImage[];
  total: number;
  offset: number;
  limit: number;
};

export type VisionUploadResult = {
  added: number;
  duplicates: number;
  rejected: string[];
  images: VisionImage[];
};

export type ExtractFramesResult = {
  candidate_frames: number;
  rejected_quality: number;
  rejected_duplicates: number;
  selected_frames: number;
  effective_interval_seconds: number;
  dataset: VisionDataset;
};

export type VisionTrainingRun = {
  id: string;
  project_id: string;
  dataset_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  trainer: string;
  base_model: string;
  preset: string;
  epochs: number;
  total_epochs: number;
  image_size: number;
  batch_size: number;
  device: string;
  progress: number;
  current_epoch: number;
  metrics: Record<string, unknown>;
  error: string | null;
  model_version_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type MetricSummary = {
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  map50?: number | null;
  map75?: number | null;
  map50_95?: number | null;
  inference_fps?: number | null;
  inference_latency_ms?: number | null;
  model_size_mb?: number | null;
};

export type PerClassMetric = MetricSummary & {
  class_index: number;
  class_name: string;
};

export type EvaluationArtifact = {
  name: string;
  url: string;
  media_type: string;
};

export type ModelEvaluation = {
  model_version_id: string;
  model_name: string;
  version: number;
  state: "completed";
  metrics: Record<string, unknown>;
  summary: MetricSummary;
  per_class: PerClassMetric[];
  confusion_matrix: number[][] | null;
  confusion_matrix_labels: string[];
  dataset_id: string;
  dataset_version: number;
  dataset_image_count: number;
  test_image_count: number;
  dataset_checksum: string | null;
  split: "test";
  image_size: number;
  base_model: string;
  preset: string;
  training_date: string;
  evaluated_at: string;
  artifacts: EvaluationArtifact[];
};

export type VisionModelVersion = {
  id: string;
  model_id: string;
  project_id: string;
  training_run_id: string;
  dataset_id: string;
  name: string;
  crop: string;
  task_type: string;
  capability_id: string;
  version: number;
  architecture: string;
  status: "candidate" | "production" | "archived";
  classes: string[];
  metrics: Record<string, unknown>;
  created_at: string;
};
