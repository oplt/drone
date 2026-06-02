import { httpRequest } from "../../../shared/api/httpClient";
import { ApiError } from "../../../shared/api/apiError";

export type WarehouseGoPreflight = {
  ready?: boolean;
  blocking?: boolean;
  checks?: Record<string, string>;
  ready_to_fly: boolean;
  bridge_ok: boolean;
  gazebo_ok: boolean | null;
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
      tracking_ok?: boolean | null;
    };
  };
  recommended_action?: string | null;
  blocking_reasons: string[];
  suggested_actions: string[];
  categories: Record<string, string>;
  note: string;
};

export async function fetchWarehousePreflight(
  token: string,
  options?: { missionLoaded?: boolean; deep?: boolean },
): Promise<WarehouseGoPreflight> {
  const params = new URLSearchParams();
  if (options?.missionLoaded) {
    params.set("mission_loaded", "true");
  }
  if (options?.deep != null) {
    params.set("deep", String(options.deep));
  }
  const query = params.toString();
  const path = query ? `/warehouse/preflight?${query}` : "/warehouse/preflight";
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
