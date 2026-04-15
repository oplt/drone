
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  token: string | null = null
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : "/" + endpoint}`;

  const headers = new Headers(options.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || `Request failed with status ${response.status}`);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export type PreflightRunResponse = {
  preflight_run_id: string;
  mission_fingerprint?: string;
  overall_status: string;
  can_start_mission: boolean;
  created_at?: number;
  expires_at?: number;
  report?: {
    mission_type?: string;
    overall_status?: string;
    base_checks?: Array<{
      name: string;
      status: string;
      message?: string | null;
    }>;
    mission_checks?: Array<{
      name: string;
      status: string;
      message?: string | null;
    }>;
    summary?: {
      failed?: number;
      warned?: number;
      passed?: number;
      total_checks?: number;
    };
  };
};

export type MissionLifecycleState =
  | "queued"
  | "running"
  | "paused"
  | "aborted"
  | "completed"
  | "failed";

export type MissionCommand = "pause" | "resume" | "abort";

export type MissionRuntimeResponse = {
  flight_id: string;
  mission_name: string;
  mission_type: string;
  state: MissionLifecycleState;
  created_at: number;
  updated_at: number;
  preflight_run_id?: string | null;
  db_flight_id?: string | null;
  last_error?: string | null;
};

export type MissionCreateResponse = {
  flight_id: string;
  status: string;
  mission_name: string;
  mission_type: string;
  waypoints_count: number;
  preflight_run_id?: string | null;
};

export type MissionCommandResponse = {
  flight_id: string;
  command_id: string;
  command: MissionCommand;
  idempotency_key: string;
  state_before: MissionLifecycleState;
  state_after: MissionLifecycleState;
  accepted: boolean;
  message: string;
  requested_at: number;
};

export type MissionCommandAuditResponse = {
  command_id: string;
  command: MissionCommand;
  idempotency_key: string;
  requested_by_user_id: number;
  requested_at: number;
  state_before: MissionLifecycleState;
  state_after: MissionLifecycleState;
  accepted: boolean;
  message: string;
  reason?: string | null;
};

export type MissionStateTransitionResponse = {
  state: string;
  entered_at: number;
  trigger: string;
  command_id?: string | null;
  command?: string | null;
  reason?: string | null;
};

export type OpsQueueSnapshot = {
  depth: number;
  capacity: number;
  utilization_pct: number;
};

export type OpsHealthResponse = {
  status: "healthy" | "degraded" | "offline";
  generated_at: number;
  telemetry: {
    running: boolean;
    source_connected: boolean;
    active_connections: number;
    last_update: number;
    last_update_age_sec?: number | null;
    has_recent_update: boolean;
    recent_threshold_sec: number;
  };
  video: {
    available: boolean;
    healthy?: boolean;
    frame_count?: number;
    fps?: number;
    resolution?: string;
    recording?: boolean;
    recording_file?: string | null;
    error?: string;
  };
  queues: {
    db_event: OpsQueueSnapshot;
    db_lifecycle: OpsQueueSnapshot;
    raw_event: OpsQueueSnapshot;
  };
  runtime_metrics: Record<string, unknown>;
  shadow: {
    shadow_mode_active: boolean;
    old_path: {
      writes_attempted: number;
      writes_ok: number;
      writes_failed: number;
      error_rate_pct: number;
    };
    new_path: {
      events_enqueued: number;
      dropped_db_events: number;
      worker_batches_completed: number;
    };
    interpretation: string;
  };
  active_mission?: {
    flight_id: string;
    mission_name: string;
    mission_type: string;
    state: string;
    updated_at?: number | null;
  } | null;
  alerts: string[];
};

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

export type WarehouseScanStartRequest = {
  field_id: number;
  mission_name?: string;
  cruise_alt?: number;
  reference_mapping_job_id?: number | null;
  corridor_spacing_m?: number;
  aisle_axis_deg?: number | null;
  clearance_m?: number;
  perimeter_offset_m?: number;
  scan_pattern?: "aisle_serpentine" | "stacked_passes" | "crosshatch" | "perimeter_aisle_hybrid";
  lane_strategy?: "serpentine" | "one_way";
  view_mode?: "forward" | "left_face" | "right_face" | "dual_face";
  layer_count?: number;
  layer_spacing_m?: number;
  ceiling_height_m?: number;
  ceiling_margin_m?: number;
  work_speed_mps?: number;
  transit_speed_mps?: number;
  scan_pause_s?: number;
  interpolate_steps_work_leg?: number;
  interpolate_steps_transit_leg?: number;
};

export type WarehouseMissionLaunchResponse = {
  field_id: number;
  field_name: string;
  preflight: PreflightRunResponse;
  mission: MissionCreateResponse;
};

export type WarehouseScannedMapAssetResponse = {
  id: number;
  type: string;
  url: string;
  created_at: string;
  meta_data?: Record<string, unknown>;
};

export type WarehouseScannedMapResponse = {
  job_id: number;
  model_id: number;
  model_version: number;
  field_id: number;
  field_name: string;
  status: string;
  created_at: string;
  finished_at?: string | null;
  boundary_lonlat: Array<[number, number] | number[]>;
  assets: WarehouseScannedMapAssetResponse[];
};

export type WarehouseMissionDefaultsResponse = {
  cruise_alt: number;
  corridor_spacing_m: number;
  aisle_axis_deg: number | null;
  clearance_m: number;
  perimeter_offset_m: number;
  scan_pattern: "aisle_serpentine" | "stacked_passes" | "crosshatch" | "perimeter_aisle_hybrid";
  lane_strategy: "serpentine" | "one_way";
  view_mode: "forward" | "left_face" | "right_face" | "dual_face";
  layer_count: number;
  layer_spacing_m: number;
  ceiling_height_m: number;
  ceiling_margin_m: number;
  work_speed_mps: number;
  transit_speed_mps: number;
  scan_pause_s: number;
  interpolate_steps_work_leg: number;
  interpolate_steps_transit_leg: number;
};

const parseErrorText = (bodyText: string): string => {
  const trimmed = bodyText.trim();
  if (!trimmed) return "";
  try {
    const parsed = JSON.parse(trimmed);
    const detail = parsed?.detail ?? parsed?.message ?? parsed?.error;
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
  } catch {
    // keep raw text fallback
  }
  return trimmed;
};

const readErrorMessage = async (response: Response): Promise<string> => {
  const bodyText = await response.text().catch(() => "");
  const parsed = parseErrorText(bodyText);
  if (parsed) return parsed;
  return `Request failed with status ${response.status}`;
};

export async function startMissionWithPreflight(
  missionPayload: Record<string, unknown>,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<{ preflight: PreflightRunResponse; mission: MissionCreateResponse }> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const preflightRes = await fetch(`${normalizedBase}/tasks/preflight/run`, {
    method: "POST",
    headers,
    body: JSON.stringify(missionPayload),
  });
  if (!preflightRes.ok) {
    throw new Error(await readErrorMessage(preflightRes));
  }

  const preflight = (await preflightRes.json()) as PreflightRunResponse;
  if (!preflight?.preflight_run_id) {
    throw new Error("Preflight run did not return a run id.");
  }
  if (!preflight.can_start_mission) {
    const failed = preflight.report?.summary?.failed;
    const status = preflight.overall_status || "FAIL";
    throw new Error(
      typeof failed === "number"
        ? `Preflight ${status}. ${failed} checks failed; mission start blocked.`
        : `Preflight ${status}. Mission start blocked.`,
    );
  }

  const missionRes = await fetch(`${normalizedBase}/tasks/missions`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      ...missionPayload,
      preflight_run_id: preflight.preflight_run_id,
    }),
  });
  if (!missionRes.ok) {
    throw new Error(await readErrorMessage(missionRes));
  }

  const mission = (await missionRes.json()) as MissionCreateResponse;
  return { preflight, mission };
}

export async function getMissionRuntime(
  flightId: string,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<MissionRuntimeResponse> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(`${normalizedBase}/tasks/missions/${encodeURIComponent(flightId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function sendMissionCommand(
  flightId: string,
  command: MissionCommand,
  token: string,
  idempotencyKey: string,
  reason?: string,
  apiBase: string = API_BASE_URL,
): Promise<MissionCommandResponse> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(
    `${normalizedBase}/tasks/missions/${encodeURIComponent(flightId)}/commands/${command}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        idempotency_key: idempotencyKey,
        reason: reason ?? null,
      }),
    },
  );
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function getMissionCommandAudit(
  flightId: string,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<MissionCommandAuditResponse[]> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(
    `${normalizedBase}/tasks/missions/${encodeURIComponent(flightId)}/commands`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function getMissionStateTransitions(
  flightId: string,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<MissionStateTransitionResponse[]> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(
    `${normalizedBase}/tasks/missions/${encodeURIComponent(flightId)}/transitions`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function getOpsHealth(
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<OpsHealthResponse> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(`${normalizedBase}/telemetry/ops-health`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function getIrrigationMissionSummary(
  missionId: string,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<IrrigationMissionSummary> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(
    `${normalizedBase}/irrigation/missions/${encodeURIComponent(missionId)}/summary`,
    {
      headers: { Authorization: `Bearer ${token}` },
      credentials: "include",
    },
  );
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function triggerIrrigationMissionProcessing(
  missionId: string,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<IrrigationProcessedFieldLayer> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(
    `${normalizedBase}/irrigation/missions/${encodeURIComponent(missionId)}/process`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      credentials: "include",
    },
  );
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function startWarehouseScan(
  payload: WarehouseScanStartRequest,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<WarehouseMissionLaunchResponse> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(`${normalizedBase}/warehouse/missions/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function listWarehouseScannedMaps(
  token: string,
  apiBase: string = API_BASE_URL,
  fieldId?: number | null,
): Promise<WarehouseScannedMapResponse[]> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const params = new URLSearchParams();
  if (typeof fieldId === "number" && Number.isFinite(fieldId)) {
    params.set("field_id", String(fieldId));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${normalizedBase}/warehouse/scanned-maps${suffix}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function getWarehouseMissionDefaults(
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<WarehouseMissionDefaultsResponse> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(`${normalizedBase}/warehouse/mission-defaults`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}

export async function updateWarehouseMissionDefaults(
  payload: WarehouseMissionDefaultsResponse,
  token: string,
  apiBase: string = API_BASE_URL,
): Promise<WarehouseMissionDefaultsResponse> {
  const normalizedBase = apiBase.replace(/\/$/, "");
  const res = await fetch(`${normalizedBase}/warehouse/mission-defaults`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.json();
}
