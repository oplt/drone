import type { NvbloxLiveStatus } from "../../api/warehouseLiveMapApi";
import type { WarehouseLiveVoxelMapState } from "../../hooks/useWarehouseLiveVoxelMap";

export function formatLiveVoxelTime(value: string | null): string {
  if (!value) return "--";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleTimeString();
}

export const LIVE_VOXEL_STATUS_LABELS: Record<
  WarehouseLiveVoxelMapState["connectionState"],
  string
> = {
  empty: "empty",
  connecting: "connecting",
  live: "live",
  stale: "stale",
  reconnecting: "reconnecting",
  finalized: "finalized",
  failed: "failed",
};

export function liveVoxelStatusColor(
  status: WarehouseLiveVoxelMapState["connectionState"],
): "success" | "warning" | "error" | "default" {
  if (status === "live" || status === "finalized") return "success";
  if (status === "stale" || status === "reconnecting" || status === "connecting") {
    return "warning";
  }
  if (status === "failed") return "error";
  return "default";
}

export function liveVoxelNvbloxStatusColor(
  status: NvbloxLiveStatus | null | undefined,
): "success" | "warning" | "error" | "default" {
  if (status === "live") return "success";
  if (status === "warming" || status === "degraded") return "warning";
  if (status === "error") return "error";
  return "default";
}

export function resolveLiveVoxelNvbloxStatus(
  state: WarehouseLiveVoxelMapState,
): NvbloxLiveStatus {
  if (state.health.nvblox_status) return state.health.nvblox_status;
  return state.health.nvblox_ready ? "live" : "off";
}

export function liveVoxelOverlayCopy(state: WarehouseLiveVoxelMapState): {
  title: string;
  body: string;
} {
  const title =
    state.connectionState === "reconnecting"
      ? "Reconnecting"
      : state.connectionState === "stale"
        ? "Stream stale"
        : state.connectionState === "failed"
          ? "Live map failed"
          : "Waiting for live voxel updates";
  const body =
    state.connectionState === "failed"
      ? (state.error ?? "Stream unavailable.")
      : state.connectionState === "reconnecting"
        ? "Keeping the last rendered chunks visible."
        : state.connectionState === "stale"
          ? "No voxel update has arrived recently."
          : "Start a warehouse flight or manual mapping session.";
  return { title, body };
}
