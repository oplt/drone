export type MappingAssetRecord = {
  id: number;
  type: string;
  url: string;
  meta_data?: Record<string, unknown>;
  created_at?: string;
};

export type MappingJobStatus =
  | "pending"
  | "uploading"
  | "processing"
  | "ready"
  | "failed";

export type MappingJobRecord = {
  job_id: number;
  field_id: number;
  model_id: number;
  status: MappingJobStatus;
  progress: number;
  error?: string | null;
  processor: string;
  processor_task_id?: string | null;
  assets: MappingAssetRecord[];
};

export type MappingJobArtifacts = {
  orthomosaic: boolean;
  dsm: boolean;
  dtm: boolean;
  textured_mesh: boolean;
  point_cloud: boolean;
  xyz_tiles: boolean;
};

export const FAST_3D_MAP_WEBODM_OPTIONS = {
  "auto-boundary": true,
  "dem-resolution": 10,
  "feature-quality": "medium",
  gltf: true,
  "mesh-size": 100000,
  "orthophoto-resolution": 10,
  "pc-quality": "low",
  "skip-report": true,
  "use-3dmesh": true,
} as const;
