import { httpRequest } from "../../../shared/api/httpClient";

export type WarehouseFlightSubsystemStatus = "OK" | "WARN" | "FAIL" | "WAITING" | "UNKNOWN";

export type WarehouseFlightSubsystem = {
  status: WarehouseFlightSubsystemStatus;
  message: string;
  last_seen_ms?: number | null;
  stable_for_ms?: number | null;
  required_stable_ms?: number | null;
  costmap_age_ms?: number | null;
  details?: Record<string, unknown>;
};

export type WarehouseFlightReadiness = {
  ready_to_arm: boolean;
  ready_to_takeoff: boolean;
  ready_for_autonomy: boolean;
  overall_status: string;
  current_state: string;
  subsystems: Record<string, WarehouseFlightSubsystem>;
  blocking_reasons: string[];
  updated_at: string;
  slam_stable_for_ms: number;
  slam_required_stable_ms: number;
  perception_stable_for_ms?: number;
  perception_required_stable_ms?: number;
};

export type WarehouseFlightStartPayload = {
  warehouse_map_id: number;
  mission_name?: string;
  sensor_rig_id?: number | null;
  dock_id?: number | null;
  reference_mapping_job_id?: number | null;
  work_speed_mps?: number | null;
  cruise_alt?: number | null;
};

export type WarehouseFlightStartResponse = {
  accepted: boolean;
  reason?: string | null;
  blocking_reasons?: string[];
  readiness?: WarehouseFlightReadiness | null;
  launch?: Record<string, unknown> | null;
};

export type WarehouseFlightCommand = "pause" | "resume" | "abort" | "land" | "rth";

export async function fetchWarehouseFlightReadiness(
  token: string,
  options?: { missionLoaded?: boolean },
): Promise<WarehouseFlightReadiness> {
  const params = new URLSearchParams();
  if (options?.missionLoaded) {
    params.set("mission_loaded", "true");
  }
  const query = params.toString();
  const path = query ? `/warehouse/flight/readiness?${query}` : "/warehouse/flight/readiness";
  return httpRequest<WarehouseFlightReadiness>(path, { token });
}

export async function startWarehouseFlight(
  payload: WarehouseFlightStartPayload,
  token: string,
): Promise<WarehouseFlightStartResponse> {
  return httpRequest<WarehouseFlightStartResponse>("/warehouse/flight/start", {
    method: "POST",
    token,
    body: payload,
  });
}

export async function sendWarehouseFlightCommand(
  command: WarehouseFlightCommand,
  token: string,
): Promise<{ accepted: boolean; message: string }> {
  return httpRequest<{ accepted: boolean; message: string }>("/warehouse/flight/command", {
    method: "POST",
    token,
    body: { command },
  });
}
