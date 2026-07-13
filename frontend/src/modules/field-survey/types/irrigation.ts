export type IrrigationCaptureRecord = {
  id: number;
  mission_id: string;
  image_uri: string;
  timestamp_utc: string;
  lat: number;
  lon: number;
  alt_m?: number | null;
  yaw_deg?: number | null;
  pitch_deg?: number | null;
  roll_deg?: number | null;
  waypoint_seq?: number | null;
  frame_width?: number | null;
  frame_height?: number | null;
  meta_data?: Record<string, unknown>;
};

export type IrrigationAnomalyZone = {
  id: number;
  type: "under_irrigated" | "overwatered" | "uneven_distribution" | string;
  severity: number;
  confidence: number;
  area_m2?: number | null;
  centroid_lat: number;
  centroid_lon: number;
  polygon_geojson: {
    type: "Polygon";
    coordinates: number[][][];
  };
  evidence_image_ids?: Array<number | string>;
  meta_data?: Record<string, unknown>;
};

export type IrrigationInspectionPoint = {
  id: number;
  zone_id?: number | null;
  lat: number;
  lon: number;
  label: string;
  priority: number;
  meta_data?: Record<string, unknown>;
};

export type IrrigationProcessedFieldLayer = {
  id: number;
  mission_id: string;
  status: "pending" | "running" | "completed" | "failed" | string;
  capture_count: number;
  stitched_image_uri?: string | null;
  footprints_geojson?: Record<string, unknown>;
  tile_manifest?: {
    kind?: string;
    image_uri?: string;
    bounds?: {
      north: number;
      south: number;
      east: number;
      west: number;
    };
    preview_size_px?: {
      width: number;
      height: number;
    };
  } | null;
  bounds_geojson?: Record<string, unknown>;
  resolution_m_per_px?: number | null;
  summary?: Record<string, unknown>;
  error?: string | null;
  completed_at?: string | null;
};

export type IrrigationMissionSummary = {
  mission_id: string;
  status: string;
  capture_count: number;
  captures: IrrigationCaptureRecord[];
  layer?: IrrigationProcessedFieldLayer | null;
  anomaly_zones: IrrigationAnomalyZone[];
  inspection_points: IrrigationInspectionPoint[];
  summary?: {
    status?: string;
    total_anomaly_count?: number;
    counts_by_type?: {
      under_irrigated?: number;
      overwatered?: number;
      uneven_distribution?: number;
    };
    average_confidence?: number;
    capture_count?: number;
  } & Record<string, unknown>;
};

export type IrrigationProcessingJob = {
  id: string;
  mission_id: string;
  input_checksum: string;
  force: boolean;
  status: "queued" | "running" | "completed" | "failed" | string;
  celery_task_id?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};
