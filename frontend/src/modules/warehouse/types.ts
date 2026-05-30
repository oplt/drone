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
};
