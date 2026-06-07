import { httpRequest } from "../../../shared/api/httpClient";
import { ApiError } from "../../../shared/api/apiError";

export type WarehouseGoPreflight = {
  ready?: boolean;
  blocking?: boolean;
  checks?: Array<{ id: string; label?: string; status: string }> | Record<string, string>;
  ready_to_fly: boolean;
  service_health?: boolean;
  ros_graph_ready?: boolean;
  mapping_ok?: boolean | null;
  primary_blocker?: string | null;
  blockers?: string[];
  diagnostics_age_ms?: number | null;
  mode?: string;
  localization_mode?: string;
  topic_health?: Record<string, unknown>;
  tf_health?: Record<string, unknown>;
  stability_window_ms?: number;
  required_stability_window_ms?: number;
  bridge_ok: boolean;
  source_transport_ok: boolean | null;
  sensors_ok: boolean;
  odom_ok: boolean;
  localization_ok: boolean;
  tf_ok: boolean;
  nvblox_ok: boolean | null;
  stability_ok: boolean;
  vehicle_link_ok: boolean;
  telemetry_stream_ok: boolean;
  battery_ok: boolean;
  perception_stable_for_ms: number;
  perception_required_stable_ms: number;
  ros_topic_count: number | null;
  warehouse_bridge_state?: string;
  bridge_url?: string | null;
  last_error?: string | null;
  restart_count?: number;
  diagnostics?: {
    bridge?: {
      process_state?: string | null;
      api_reachable?: boolean;
      health_sample_age_ms?: number | null;
      health_sample_max_age_ms?: number;
      health_probe_in_progress?: boolean;
      deep_ready?: boolean;
      status?: string;
      message?: string;
    };
    topics?: {
      required_missing?: string[];
      required_unhealthy?: string[];
      deferred_missing?: string[];
      by_category?: Record<
        string,
        {
          topic?: string;
          status?: string;
          verify_cmd?: string;
          alternatives?: string[];
        }
      >;
      topic_diagnostics?: Record<string, unknown>;
    };
    stability?: {
      stable_for_ms?: number;
      required_ms?: number;
      remaining_ms?: number;
      last_reset_reason?: string | null;
      last_successful_stable_ms?: number;
      localization_mode?: string;
      tracking_ok?: boolean | null;
      odometry_topic?: string;
    };
    freshness?: {
      health_sample_age_ms?: number | null;
      health_sample_max_age_ms?: number;
      stale_warn_threshold_ms?: number;
      diagnostics_age_ms?: number | null;
      diagnostics_stale?: boolean;
    };
    cache?: {
      from_cache?: boolean;
      age_ms?: number | null;
      refresh_in_progress?: boolean;
      refresh_run_id?: string | null;
      run_id?: string | null;
    };
    timings?: {
      refresh_in_progress?: boolean;
      cache_age_ms?: number | null;
      from_cache?: boolean;
    };
  };
  recommended_action?: string | null;
  blocking_reasons: string[];
  suggested_actions: string[];
  categories: Record<string, string>;
  note: string;
};

export type WarehousePreflightRefresh = {
  run_id: string;
  status: "running" | "complete" | "failed" | string;
  deep: boolean;
  force: boolean;
  mission_loaded: boolean;
  started_at: string;
  finished_at?: string | null;
  error?: string | null;
  snapshot?: WarehouseGoPreflight | null;
};

function queryString(options?: {
  missionLoaded?: boolean;
  deep?: boolean;
  force?: boolean;
  freshVehicleProbe?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.missionLoaded) {
    params.set("mission_loaded", "true");
  }
  if (options?.deep != null) {
    params.set("deep", String(options.deep));
  }
  if (options?.force) {
    params.set("force", "true");
  }
  if (options?.freshVehicleProbe) {
    params.set("fresh_vehicle_probe", "true");
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function fetchWarehousePreflight(
  token: string,
  options?: {
    missionLoaded?: boolean;
    deep?: boolean;
    force?: boolean;
    freshVehicleProbe?: boolean;
  },
): Promise<WarehouseGoPreflight> {
  const path = `/warehouse/preflight${queryString(options)}`;
  try {
    return await httpRequest<WarehouseGoPreflight>(path, { token });
  } catch (error) {
    if (
      error instanceof ApiError &&
      (error.status === 503 || error.status === 424)
    ) {
      const body = error.body as
        | { detail?: unknown; error?: { code?: string; details?: unknown } }
        | null;
      const detail = body?.detail ?? body?.error?.details;
      if (detail && typeof detail === "object") {
        return detail as WarehouseGoPreflight;
      }
    }
    throw error;
  }
}

export async function refreshWarehousePreflight(
  token: string,
  options?: {
    missionLoaded?: boolean;
    deep?: boolean;
    force?: boolean;
    freshVehicleProbe?: boolean;
  },
): Promise<WarehousePreflightRefresh> {
  return httpRequest<WarehousePreflightRefresh>(
    `/warehouse/preflight/refresh${queryString(options)}`,
    { method: "POST", token },
  );
}

export async function fetchWarehousePreflightRun(
  token: string,
  runId: string,
): Promise<WarehousePreflightRefresh> {
  return httpRequest<WarehousePreflightRefresh>(
    `/warehouse/preflight/runs/${encodeURIComponent(runId)}`,
    { token },
  );
}
