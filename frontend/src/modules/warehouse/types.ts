export type WarehouseMapOut = {
  id: number;
  name: string;
  area_m2: number | null;
  created_at: string;
  polygon_local_m: [number, number][];
};

export type CreateWarehouseMapPayload = {
  name: string;
  width_m: number;
  length_m: number;
};

export type WarehouseDockPose = {
  x_m: number;
  y_m: number;
  z_m: number;
  yaw_deg?: number | null;
};

export type WarehouseDockStation = {
  id: number;
  name: string;
  marker_id: string | null;
  marker_family: string | null;
  marker_size_m: number | null;
  marker_pose_covariance: number[];
  marker_visible: boolean | null;
  last_observed_at: string | null;
  charger_type: string | null;
  pose: WarehouseDockPose;
  entry_pose: WarehouseDockPose;
  exit_pose: WarehouseDockPose;
  active: boolean;
  created_at: string;
};

export type WarehouseDockPayload = {
  name: string;
  marker_id?: string | null;
  marker_family?: string | null;
  marker_size_m?: number | null;
  charger_type?: string | null;
  precision_required?: boolean;
  pose: WarehouseDockPose;
  entry_pose: WarehouseDockPose;
  exit_pose: WarehouseDockPose;
};

export type WarehouseDockUpdatePayload = Partial<WarehouseDockPayload>;

export type WarehouseSensorRig = {
  id: number;
  name: string;
  camera_model: string;
  stereo_baseline_m: number | null;
  intrinsics_url: string | null;
  extrinsics_url: string | null;
  imu_transform_json: Record<string, unknown>;
  firmware_version: string | null;
  isaac_ros_version: string | null;
  calibration_status: "missing" | "pending" | "valid" | "expired" | "failed" | string;
  calibration_hash: string | null;
  calibration_meta: Record<string, unknown>;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type CreateWarehouseSensorRigPayload = {
  name: string;
  camera_model: string;
  stereo_baseline_m?: number | null;
  intrinsics_url?: string | null;
  extrinsics_url?: string | null;
  firmware_version?: string | null;
  isaac_ros_version?: string | null;
  imu_transform_json?: Record<string, unknown>;
};

export type UpdateWarehouseSensorRigCalibrationPayload = {
  calibration_status: "missing" | "pending" | "valid" | "expired" | "failed";
  calibration_hash?: string | null;
  intrinsics_url?: string | null;
  extrinsics_url?: string | null;
  imu_transform_json?: Record<string, unknown> | null;
  calibration_meta?: Record<string, unknown>;
};

export type WarehouseSensorRigHealth = {
  sensor_rig: WarehouseSensorRig;
  perception: {
    configured: boolean;
    reachable: boolean;
    ready: boolean;
    status: string;
    profile?: string | null;
    detail?: string | null;
    components: Record<string, unknown>;
  };
  ready: boolean;
  blockers: string[];
  warnings?: string[];
};

export type SensorTopicFrames = {
  odom: string;
  base_link: string;
  camera: string;
};

export type SensorTopicProfile = {
  id: string;
  name: string;
  profile: string;
  source_topics: Record<string, string>;
  contract_topics: Record<string, string>;
  frames: SensorTopicFrames;
  use_sim_time: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type SensorTopicProfilePayload = {
  name: string;
  profile: string;
  source_topics: Record<string, string>;
  contract_topics: Record<string, string>;
  frames: SensorTopicFrames;
  use_sim_time: boolean;
};

export type SensorTopicValidationRequest = {
  profile?: string | null;
  source_topics?: Record<string, string>;
  check_hz?: boolean;
  keys?: string[] | null;
};

export type SensorTopicTopicValidation = {
  key: string;
  topic: string;
  expected_type?: string | null;
  actual_type?: string | null;
  publisher_count?: number;
  hz?: number | null;
  status:
    | "OK"
    | "MISSING"
    | "TYPE_MISMATCH"
    | "NO_PUBLISHERS"
    | "NOT_PUBLISHING"
    | "UNKNOWN";
  detail?: string | null;
};

export type SensorTopicValidationResult = {
  profile: string;
  ros_topics: string[];
  discovered_topics: string[];
  topics: SensorTopicTopicValidation[];
};

export type SensorTopicDiscoveryRequest = {
  profile?: string | null;
};

export type SensorTopicDiscoveryResult = {
  profile: string;
  transport: string;
  source_topics: Record<string, string>;
  discovered_topics: string[];
  discovery_hint?: string | null;
  used_profile_defaults?: boolean;
};
