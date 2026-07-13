import { httpRequest } from "../../../shared/api/httpClient";
import type { PageResponse } from "../../../shared/api/pagination";

export type WarehouseCoordinateFrame = {
  id: number;
  warehouse_map_id: number;
  version: number;
  parent_frame_id: "warehouse_map";
  child_frame_id: string;
  units: "m";
  axis_convention: "ENU";
  handedness: "right";
  transform: {
    translation: { x: number; y: number; z: number };
    rotation: { x: number; y: number; z: number; w: number };
  };
  source: string;
  status: "locked";
  confidence: number | null;
  covariance: number[];
  created_at: string;
  locked_at: string;
  superseded_at: null;
};

export async function fetchActiveWarehouseCoordinateFrame(
  warehouseMapId: number,
  token?: string | null,
): Promise<WarehouseCoordinateFrame> {
  return httpRequest<WarehouseCoordinateFrame>(
    `/warehouse/maps/${warehouseMapId}/coordinate-frames/active`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export type WarehouseFrameDefinition = {
  frame_id: string;
  parent_frame_id: string | null;
  role: "world" | "motion" | "body" | "sensor" | "semantic";
  publisher:
    | "localization"
    | "odometry"
    | "calibration"
    | "joint_state"
    | "optional";
  required: boolean;
  persistent_geometry: boolean;
  units: "m";
  axis_convention: string;
  handedness: "right";
};

export type WarehouseFrameContract = {
  schema_version: 1;
  checksum_sha256: string;
  frames: WarehouseFrameDefinition[];
  active_revision: Pick<
    WarehouseCoordinateFrame,
    | "id"
    | "version"
    | "parent_frame_id"
    | "child_frame_id"
    | "status"
    | "transform"
  > | null;
};

export async function fetchWarehouseFrameContract(
  warehouseMapId: number,
  token?: string | null,
): Promise<WarehouseFrameContract> {
  return httpRequest<WarehouseFrameContract>(
    `/warehouse/maps/${warehouseMapId}/frame-contract`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export type WarehouseCoordinateDiagnostics = {
  warehouse_map_id: number;
  generated_at: string;
  mission_ready: boolean;
  coordinate_frame: {
    id: number;
    version: number;
    status: string;
    parent_frame_id: string;
    child_frame_id: string;
    confidence: number | null;
    localization_method: string;
    transform_checksum: string;
    locked_at: string | null;
    transform_age_ms: number | null;
  } | null;
  latest_coordinate_frame: WarehouseCoordinateDiagnostics["coordinate_frame"];
  layout_version: {
    id: number;
    version: number;
    revision: number;
    status: string;
    coordinate_frame_id: number;
    provenance_status: string;
    locked_at: string | null;
  } | null;
  latest_layout_version: WarehouseCoordinateDiagnostics["layout_version"];
  localization_evidence: {
    age_s: number;
    max_position_std_m: number;
    confidence: number;
    checksum_sha256: string;
  } | null;
  entity_counts: Record<string, number>;
  frame_contract_checksum: string | null;
  ros_map_odom_tf?: {
    tf_ok?: boolean;
    parent_frame?: string;
    child_frame?: string;
    detail?: string | null;
  } | null;
  ros_tf_tree?: {
    tf_ok?: boolean;
    edge_count?: number;
    ok_count?: number;
    missing_edges?: string[];
    edges?: Array<{
      parent_frame: string;
      child_frame: string;
      tf_ok: boolean;
      detail?: string | null;
    }>;
  } | null;
  slam_localization?: {
    healthy?: boolean;
    confidence?: number;
    age_ms?: number;
  } | null;
  provisional_epoch?: {
    epoch_id?: string;
    revision?: number;
    stale?: boolean;
    confidence?: number;
  } | null;
  blocking_issues: Array<{ code: string; message: string; severity: string }>;
  warnings: Array<{ code: string; message: string; severity: string }>;
};

export async function fetchWarehouseCoordinateDiagnostics(
  warehouseMapId: number,
  token?: string | null,
  signal?: AbortSignal,
): Promise<WarehouseCoordinateDiagnostics> {
  return httpRequest<WarehouseCoordinateDiagnostics>(
    `/warehouse/maps/${warehouseMapId}/coordinate-diagnostics`,
    { token, signal, skipUnauthorizedRedirect: true },
  );
}

export async function syncWarehouseCoordinateFrameToRos(
  warehouseMapId: number,
  token?: string | null,
): Promise<{ synced: boolean; detail: string }> {
  return httpRequest<{ synced: boolean; detail: string }>(
    `/warehouse/maps/${warehouseMapId}/coordinate-frames/sync-ros`,
    { method: "POST", token, skipUnauthorizedRedirect: true },
  );
}

export type WarehouseLocalPoint = {
  frame_id?: string;
  x_m: number;
  y_m: number;
  z_m: number;
};

export type WarehouseLocalPose = WarehouseLocalPoint & {
  // Optional while editing legacy yaw-only drafts; API responses always include these.
  orientation?: WarehouseQuaternion;
  roll_deg?: number;
  pitch_deg?: number;
  yaw_deg: number;
};

export type WarehouseQuaternion = {
  x: number;
  y: number;
  z: number;
  w: number;
};

export type WarehouseSensorAim = {
  frame_id: "warehouse_map";
  sensor_frame_id: string;
  aim_point_local_json: WarehouseLocalPoint;
  orientation: WarehouseQuaternion;
  roll_deg: number;
  pitch_deg: number;
  yaw_deg: number;
};

export type WarehouseShelfNormal = {
  frame_id?: string;
  x: number;
  y: number;
  z?: number;
};

export type WarehouseScanTarget = {
  id: number;
  warehouse_map_id: number;
  layout_version_id: number | null;
  provenance_status: "auto" | "manual" | "confirmed";
  bin_id: number | null;
  reference_model_id: number | null;
  dock_station_id: number | null;
  aisle_code: string;
  rack_code: string | null;
  shelf_level: number | null;
  bin_code: string | null;
  sku: string | null;
  barcode: string | null;
  product_name: string | null;
  target_point_local_json: WarehouseLocalPoint;
  scan_pose_local_json: WarehouseLocalPose;
  sensor_aim_json?: WarehouseSensorAim | null;
  shelf_normal_local_json: WarehouseShelfNormal | null;
  standoff_m: number;
  hover_time_s: number;
  scan_timeout_s: number;
  priority: number;
  active: boolean;
  clearance_status: "active" | "needs_review" | "rejected";
  clearance_m?: number | null;
  clearance_source?: string | null;
  created_at: string;
  updated_at: string;
};

export type WarehouseScanTargetPayload = {
  bin_id?: number;
  coordinate_frame_id?: number;
  aisle_code: string;
  rack_code?: string | null;
  shelf_level?: number | null;
  bin_code?: string | null;
  sku?: string | null;
  barcode?: string | null;
  product_name?: string | null;
  target_point_local_json: WarehouseLocalPoint;
  scan_pose_local_json: WarehouseLocalPose;
  sensor_aim_json?: WarehouseSensorAim | null;
  shelf_normal_local_json?: WarehouseShelfNormal | null;
  standoff_m?: number;
  hover_time_s?: number;
  scan_timeout_s?: number;
  priority?: number;
  active?: boolean;
};

export type WarehouseLayoutBin = {
  id: number;
  aisle_code: string;
  rack_code: string;
  shelf_level: number;
  bin_code: string;
  geometry: Record<string, unknown>;
};

export type WarehouseLayout = {
  id: number;
  warehouse_map_id: number;
  coordinate_frame_id: number;
  version: number;
  status: string;
  source: string;
  provenance_status: "auto" | "manual" | "confirmed";
  artifact_set_id: number | null;
  input_checksum: string | null;
  algorithm_version: string | null;
  created_at: string;
  locked_at: string | null;
  bins: WarehouseLayoutBin[];
  safety_zones: Array<{
    id: number;
    code: string;
    kind: string;
    geometry: Record<string, unknown>;
    min_z_m: number | null;
    max_z_m: number | null;
    active: boolean;
  }>;
};

export async function fetchActiveWarehouseLayout(
  warehouseMapId: number,
  token?: string | null,
  signal?: AbortSignal,
): Promise<WarehouseLayout> {
  return httpRequest<WarehouseLayout>(
    `/warehouse/maps/${warehouseMapId}/layouts/active`,
    { token, signal, skipUnauthorizedRedirect: true },
  );
}

export type WarehouseInspectionMission = {
  id: number;
  warehouse_map_id: number;
  name: string;
  status: string;
  scan_mode: "barcode" | "product_photo" | "visual_check" | "mixed" | string;
  return_to_dock: boolean;
  target_ids: number[];
  plan_checksum: string | null;
  approval_status: "pending" | "approved" | "rejected";
  approved_at: string | null;
  runtime_policy: Record<string, unknown>;
  waypoints: Array<{
    target_id: number;
    purpose: string;
    pose: WarehouseLocalPose;
    hover_time_s: number;
    scan_timeout_s: number;
    metadata: Record<string, unknown>;
  }>;
  created_at: string;
  updated_at: string;
};

export type WarehouseInspectionResult = {
  id: number;
  mission_id: number;
  target_id: number;
  status: string;
  expected_barcode: string | null;
  detected_barcode: string | null;
  confidence: number | null;
  image_asset_id: number | null;
  video_asset_id: number | null;
  drone_pose_local_json: WarehouseLocalPose | null;
  error_message: string | null;
  scanned_at: string;
};

export type WarehouseInspectionResultPage =
  PageResponse<WarehouseInspectionResult>;

export type WarehouseStructureAisle = {
  code: string;
  centerline_world: [number, number, number, number];
  width_m: number;
  z_min: number;
  z_max: number;
};

export type WarehouseStructureRack = {
  code: string;
  row_v: number;
  center_world: [number, number, number];
  length_m: number;
  depth_m: number;
  z_min: number;
  z_max: number;
  faces: string[];
};

export type WarehouseStructureSummary = {
  frame_id?: string;
  floor_z?: number;
  axis_deg?: number;
  height_band_m?: [number, number];
  aisles?: WarehouseStructureAisle[];
  racks?: WarehouseStructureRack[];
  counts?: {
    aisles?: number;
    racks?: number;
    targets?: number;
    rejected_clearance?: number;
    active_targets?: number;
    review_targets?: number;
    candidate_targets?: number;
  };
  quality?: {
    status?: "ready" | "needs_review" | "failed";
    confidence?: number;
    reasons?: string[];
    active_target_count?: number;
    candidate_count?: number;
    rejected_clearance?: number;
    rejection_ratio?: number;
    targets_per_rack?: number | null;
    clearance_source?: string;
    failure_reason_codes?: string[];
  };
  params?: Record<string, number | null>;
  coordinate_setup_status?: "draft" | "active";
  manual_review_required?: boolean;
  target_counts?: {
    candidate?: number;
    active?: number;
    needs_review?: number;
    rejected?: number;
  };
  diagnostics?: {
    esdf_available?: boolean;
    esdf_topic?: string | null;
    occupancy_available?: boolean;
    occupancy_topic?: string | null;
    missing_esdf_topic?: boolean;
    missing_occupancy_grid?: boolean;
  };
};

export type WarehouseStructureResponse = {
  status:
    | "not_started"
    | "queued"
    | "running"
    | "ready"
    | "needs_review"
    | "failed";
  warehouse_map_id: number;
  model_id: number | null;
  client_flight_id?: string | null;
  task_id?: string | null;
  error_message?: string | null;
  generated_at: string | null;
  target_count: number;
  active_target_count?: number;
  review_target_count?: number;
  rejected_target_count?: number;
  coordinate_setup_status?: "draft" | "active" | null;
  manual_review_required?: boolean;
  target_counts?: Record<string, number>;
  quality_status?: "ready" | "needs_review" | "failed" | null;
  quality_reasons?: string[];
  failure_reason_codes?: string[];
  confidence?: number | null;
  debug_artifact_url?: string | null;
  debug_artifact_path?: string | null;
  summary: WarehouseStructureSummary;
};

export type WarehouseStructureExtractParams = {
  voxel_m?: number;
  grid_res_m?: number;
  bin_pitch_m?: number;
  standoff_m?: number;
  drone_radius_m?: number;
  clearance_margin_m?: number;
  min_aisle_width_m?: number;
  shelf_min_spacing_m?: number;
  max_shelf_levels?: number;
  max_bins_per_rack_face?: number;
  min_surface_points?: number;
  min_target_spacing_m?: number;
  review_clearance_m?: number;
  rack_template_bin_count?: number;
  rack_template_bay_width_m?: number;
  rack_template_shelf_levels_m?: number[];
  axis_deg?: number;
};

export type WarehouseStructureExtractResponse = {
  status: "queued";
  warehouse_map_id: number;
  model_id: number;
  client_flight_id: string;
  task_id: string | null;
};

export type WarehouseStructureDryRunResponse = WarehouseStructureResponse & {
  status: "ready" | "needs_review" | "failed";
  coordinate_frame_id?: number | null;
};

export async function fetchWarehouseStructure(
  warehouseMapId: number,
  token?: string | null,
  signal?: AbortSignal,
): Promise<WarehouseStructureResponse> {
  return httpRequest<WarehouseStructureResponse>(
    `/warehouse/maps/${warehouseMapId}/structure`,
    { token, signal, skipUnauthorizedRedirect: true },
  );
}

export async function extractWarehouseStructure(
  warehouseMapId: number,
  params: WarehouseStructureExtractParams = {},
  token?: string | null,
): Promise<WarehouseStructureExtractResponse> {
  return httpRequest<WarehouseStructureExtractResponse>(
    `/warehouse/maps/${warehouseMapId}/structure/extract`,
    { method: "POST", body: params, token, skipUnauthorizedRedirect: true },
  );
}

export async function dryRunWarehouseStructure(
  warehouseMapId: number,
  params: WarehouseStructureExtractParams = {},
  token?: string | null,
): Promise<WarehouseStructureDryRunResponse> {
  return httpRequest<WarehouseStructureDryRunResponse>(
    `/warehouse/maps/${warehouseMapId}/structure/dry-run`,
    { method: "POST", body: params, token, skipUnauthorizedRedirect: true },
  );
}

export async function computeWarehouseScanPose(
  payload: {
    target_point: WarehouseLocalPoint;
    shelf_normal?: WarehouseShelfNormal | null;
    standoff_m?: number;
    yaw_deg?: number | null;
  },
  token?: string | null,
  signal?: AbortSignal,
): Promise<{ scan_pose: WarehouseLocalPose }> {
  return httpRequest<{ scan_pose: WarehouseLocalPose }>(
    "/warehouse/scan-targets/compute-scan-pose",
    {
      method: "POST",
      body: payload,
      token,
      signal,
      skipUnauthorizedRedirect: true,
    },
  );
}

export type WarehouseScanTargetPage = PageResponse<WarehouseScanTarget> & {
  total: number;
  /** Legacy client-only fields retained for old fixtures; server no longer emits them. */
  limit?: number;
  offset?: number;
};

export async function listWarehouseScanTargets(
  warehouseMapId: number,
  token?: string | null,
  params?: {
    limit?: number;
    offset?: number;
    cursor?: string;
    active?: boolean;
  },
  signal?: AbortSignal,
): Promise<WarehouseScanTargetPage> {
  const search = new URLSearchParams();
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.offset != null) search.set("offset", String(params.offset));
  if (params?.cursor != null) search.set("cursor", params.cursor);
  if (params?.active != null) search.set("active", String(params.active));
  const query = search.toString();
  return httpRequest<WarehouseScanTargetPage>(
    `/warehouse/maps/${warehouseMapId}/scan-targets${query ? `?${query}` : ""}`,
    { token, signal, skipUnauthorizedRedirect: true },
  );
}

export async function createWarehouseScanTarget(
  warehouseMapId: number,
  payload: WarehouseScanTargetPayload,
  token?: string | null,
): Promise<WarehouseScanTarget> {
  return httpRequest<WarehouseScanTarget>(
    `/warehouse/maps/${warehouseMapId}/scan-targets`,
    { method: "POST", body: payload, token, skipUnauthorizedRedirect: true },
  );
}

export async function updateWarehouseScanTarget(
  warehouseMapId: number,
  targetId: number,
  payload: Partial<WarehouseScanTargetPayload>,
  token?: string | null,
): Promise<WarehouseScanTarget> {
  return httpRequest<WarehouseScanTarget>(
    `/warehouse/maps/${warehouseMapId}/scan-targets/${targetId}`,
    { method: "PATCH", body: payload, token, skipUnauthorizedRedirect: true },
  );
}

export async function deleteWarehouseScanTarget(
  warehouseMapId: number,
  targetId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest<void>(
    `/warehouse/maps/${warehouseMapId}/scan-targets/${targetId}`,
    { method: "DELETE", token, skipUnauthorizedRedirect: true },
  );
}

export async function createWarehouseInspectionMission(
  payload: {
    warehouse_map_id: number;
    name: string;
    target_ids: number[];
    scan_mode: "barcode" | "product_photo" | "visual_check" | "mixed";
    optimize_order: boolean;
    return_to_dock: boolean;
  },
  token?: string | null,
): Promise<WarehouseInspectionMission> {
  return httpRequest<WarehouseInspectionMission>(
    "/warehouse/inspection-missions",
    {
      method: "POST",
      body: payload,
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function runWarehouseInspectionMissionMock(
  missionId: number,
  token?: string | null,
): Promise<WarehouseInspectionResult[]> {
  return httpRequest<WarehouseInspectionResult[]>(
    `/warehouse/inspection-missions/${missionId}/run-mock`,
    { method: "POST", token, skipUnauthorizedRedirect: true },
  );
}

export async function approveWarehouseInspectionMission(
  mission: WarehouseInspectionMission,
  token?: string | null,
): Promise<WarehouseInspectionMission> {
  if (!mission.plan_checksum)
    throw new Error("Mission preview has no checksum.");
  return httpRequest<WarehouseInspectionMission>(
    `/warehouse/inspection-missions/${mission.id}/approval`,
    {
      method: "POST",
      body: { approved: true },
      headers: { "If-Match": `"${mission.plan_checksum}"` },
      token,
      skipUnauthorizedRedirect: true,
    },
  );
}

export async function listWarehouseInspectionResults(
  missionId: number,
  token?: string | null,
  options?: { limit?: number; offset?: number },
): Promise<WarehouseInspectionResultPage> {
  const params = new URLSearchParams();
  if (options?.limit != null) params.set("limit", String(options.limit));
  if (options?.offset != null) params.set("offset", String(options.offset));
  const query = params.size > 0 ? `?${params.toString()}` : "";
  return httpRequest<WarehouseInspectionResultPage>(
    `/warehouse/inspection-missions/${missionId}/results${query}`,
    { token, skipUnauthorizedRedirect: true },
  );
}
