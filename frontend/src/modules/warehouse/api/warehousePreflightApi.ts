import { httpRequest } from "../../../shared/api/httpClient";

export type WarehouseGoPreflight = {
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
  if (options?.deep === false) {
    params.set("deep", "false");
  }
  const query = params.toString();
  const path = query ? `/warehouse/preflight?${query}` : "/warehouse/preflight";
  return httpRequest<WarehouseGoPreflight>(path, { token });
}
