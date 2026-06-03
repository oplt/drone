import { Alert, Box, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import type { WarehouseLiveHealthFlags } from "../api/warehouseLiveMapApi";
import type { WarehouseMappingStackStatus } from "../api/warehouseMissionsApi";

export type WarehouseMappingRuntimeStatus = {
  bridge_connected?: boolean;
  ready?: boolean;
  status?: string;
  detail?: string | null;
  profile?: string | null;
  vslam_tracking?: boolean | null;
  nvblox_ready?: boolean | null;
  nvblox_fps?: number | null;
  mapped_volume_m3?: number | null;
  mapped_area_m2?: number | null;
  dropped_frames?: number | null;
  depth_healthy?: boolean | null;
  disk_free_gb?: number | null;
  localization_confidence?: number | null;
  odometry_drift_m?: number | null;
  frontier_count?: number | null;
  exploration_state?: string | null;
  safety_action?: string | null;
  can_fly_warehouse_scan?: boolean | null;
  can_build_warehouse_map?: boolean | null;
  capabilities?: Record<string, boolean | null> | null;
  health_layers?: Record<string, string> | null;
  safety_reason?: string | null;
};

function chipColor(value: boolean | null | undefined): "success" | "warning" | "error" {
  if (value === true) return "success";
  if (value === false) return "error";
  return "warning";
}

function pct(value: number | null | undefined): number {
  if (typeof value !== "number") return 0;
  return Math.max(0, Math.min(100, value <= 1 ? value * 100 : value));
}

function statusLabel(status: string | undefined): string {
  switch (status) {
    case "starting":
      return "Starting";
    case "waiting_for_gazebo":
      return "Waiting for Gazebo/sensors";
    case "bridging":
      return "Bridging sensors";
    case "ready":
      return "Ready";
    case "degraded":
      return "Degraded";
    default:
      return status ?? "unknown";
  }
}

function chipColorForStatus(
  status: string | undefined,
  ready: boolean | null | undefined,
): "success" | "warning" | "error" {
  if (status === "starting" || status === "waiting_for_gazebo" || status === "bridging") {
    return "warning";
  }
  return chipColor(ready ?? false);
}

export function WarehouseMappingHealthPanel({
  status,
  liveHealth,
  mappingStackStatus,
}: {
  status?: WarehouseMappingRuntimeStatus | null;
  liveHealth?: WarehouseLiveHealthFlags | null;
  mappingStackStatus?: WarehouseMappingStackStatus | null;
}) {
  if (!status) return null;

  const confidence = pct(status.localization_confidence ?? liveHealth?.coverage_percent);
  const nvbloxReady = status.nvblox_ready ?? liveHealth?.nvblox_ready;
  const driftM = status.odometry_drift_m ?? liveHealth?.drift_estimate_m;
  const stackWaitingSensors =
    mappingStackStatus?.phase === "waiting_sensors" ||
    (mappingStackStatus?.running === true &&
      mappingStackStatus?.nvblox_running === false);
  const stackStopped =
    mappingStackStatus?.running === false &&
    mappingStackStatus?.nvblox_running !== true &&
    liveHealth?.stack_running !== true;
  const warnings = [
    status.bridge_connected === false ? "ROS bridge disconnected." : null,
    status.vslam_tracking === false ? "VSLAM tracking lost." : null,
    status.depth_healthy === false ? "Depth stream unhealthy." : null,
    stackWaitingSensors
      ? "Mapping stack waiting for Gazebo sensors (press Play or gz sim -r)."
      : stackStopped
        ? "Mapping stack stopped."
        : null,
    !stackStopped &&
    !stackWaitingSensors &&
    liveHealth?.mapping_recording === false
      ? "Mapping not recording live voxel updates yet (nvblox ESDF not publishing)."
      : null,
    typeof status.dropped_frames === "number" && status.dropped_frames > 0
      ? `${status.dropped_frames} dropped frames.`
      : null,
    typeof status.disk_free_gb === "number" && status.disk_free_gb < 10
      ? `Low disk: ${status.disk_free_gb.toFixed(1)}GB.`
      : null,
    status.safety_reason ? `Safety: ${status.safety_reason}.` : null,
  ].filter(Boolean);

  return (
    <Box sx={{ mt: 2, p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle2">ROS Mapping Health</Typography>
          <Chip
            size="small"
            label={statusLabel(status.status)}
            color={chipColorForStatus(
              status.status,
              status.can_fly_warehouse_scan ?? status.ready ?? false,
            )}
          />
          {status.capabilities?.can_map_3d === false && status.capabilities?.can_fly_warehouse_scan && (
            <Chip size="small" label="3D mapping degraded" color="warning" variant="outlined" />
          )}
          <Chip
            size="small"
            label="VSLAM"
            color={chipColor(status.vslam_tracking)}
            variant="outlined"
          />
          <Chip
            size="small"
            label="Nvblox"
            color={chipColor(nvbloxReady)}
            variant="outlined"
          />
          <Chip
            size="small"
            label="Depth"
            color={chipColor(status.depth_healthy)}
            variant="outlined"
          />
        </Stack>

        <Stack direction="row" spacing={1.5} flexWrap="wrap">
          <Metric label="Mapped" value={formatMetric(status.mapped_area_m2, "m2")} />
          <Metric label="Volume" value={formatMetric(status.mapped_volume_m3, "m3")} />
          <Metric label="Nvblox FPS" value={formatMetric(status.nvblox_fps, "fps")} />
          <Metric label="Coverage" value={formatPercentMetric(liveHealth?.coverage_percent)} />
          <Metric label="Frontiers" value={formatMetric(status.frontier_count, "")} />
          <Metric label="Drift" value={formatMetric(driftM, "m")} />
          <Metric label="Disk" value={formatMetric(status.disk_free_gb, "GB")} />
        </Stack>

        {status.exploration_state && (
          <Typography variant="caption" color="text.secondary">
            Exploration state {status.exploration_state}
            {status.safety_action ? `, action ${status.safety_action}` : ""}
          </Typography>
        )}

        <Box>
          <Typography variant="caption" color="text.secondary">
            Localization confidence {confidence.toFixed(0)}%
          </Typography>
          <LinearProgress variant="determinate" value={confidence} sx={{ mt: 0.5 }} />
        </Box>

        {status.health_layers && (
          <Typography variant="caption" color="text.secondary" component="div">
            Bridge {status.health_layers.bridge_liveness ?? "?"}
            {" · "}
            Sensors {status.health_layers.sensor_inputs ?? "?"}
            {" · "}
            SLAM {status.health_layers.slam ?? "?"}
            {" · "}
            Nvblox {status.health_layers.nvblox ?? "?"}
          </Typography>
        )}

        {warnings.length > 0 && <Alert severity="warning">{warnings.join(" ")}</Alert>}
      </Stack>
    </Box>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}

function formatMetric(value: number | null | undefined, unit: string): string {
  if (typeof value !== "number") return "--";
  return `${value.toFixed(value >= 10 ? 0 : 1)}${unit ? ` ${unit}` : ""}`;
}

function formatPercentMetric(value: number | null | undefined): string {
  if (typeof value !== "number") return "--";
  return `${pct(value).toFixed(0)} %`;
}
