import {
  Box,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import CenterFocusStrongRoundedIcon from "@mui/icons-material/CenterFocusStrongRounded";
import LayersRoundedIcon from "@mui/icons-material/LayersRounded";
import RestartAltRoundedIcon from "@mui/icons-material/RestartAltRounded";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import type { WarehouseMappingStackStatus } from "../api/warehouseMissionsApi";

function formatTime(value: string | null): string {
  if (!value) return "--";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleTimeString();
}

function metricRow(label: string, value: string) {
  return (
    <Box
      key={label}
      sx={{
        px: 1,
        py: 0.75,
        borderRadius: 1,
        border: "1px solid",
        borderColor: "divider",
        minWidth: 0,
      }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", lineHeight: 1.2 }}
      >
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
        {value}
      </Typography>
    </Box>
  );
}

const STATUS_LABELS: Record<
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

function statusColor(
  status: WarehouseLiveVoxelMapState["connectionState"],
): "success" | "warning" | "error" | "default" {
  if (status === "live" || status === "finalized") return "success";
  if (
    status === "stale" ||
    status === "reconnecting" ||
    status === "connecting"
  ) {
    return "warning";
  }
  if (status === "failed") return "error";
  return "default";
}

export function WarehouseLiveVoxelHeader({
  state,
  cachedBytes,
}: {
  state: WarehouseLiveVoxelMapState;
  cachedBytes: number;
}) {
  return (
    <Stack
      direction="row"
      justifyContent="space-between"
      alignItems="center"
      flexWrap="wrap"
    >
      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
        <Typography variant="subtitle2" color="text.secondary">
          Stream
        </Typography>
        <Chip
          size="small"
          label={STATUS_LABELS[state.connectionState]}
          color={statusColor(state.connectionState)}
        />
        {state.finalizedScanJobId != null && (
          <Chip
            size="small"
            variant="outlined"
            label={`saved #${state.finalizedScanJobId}`}
          />
        )}
        <Chip
          size="small"
          variant="outlined"
          label={`${state.chunks.length} chunks`}
        />
        <Chip
          size="small"
          variant="outlined"
          label={`${(cachedBytes / 1048576).toFixed(1)} MB cached`}
        />
      </Stack>
      <Stack direction="row" spacing={0.5}>
        <Tooltip title="Layer visibility">
          <IconButton size="small" aria-label="Layer visibility">
            <LayersRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Follow drone">
          <IconButton size="small" aria-label="Follow drone">
            <CenterFocusStrongRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Reset camera">
          <IconButton size="small" aria-label="Reset camera">
            <RestartAltRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  );
}

export function WarehouseLiveVoxelMetrics({
  state,
  mappingStackStatus,
}: {
  state: WarehouseLiveVoxelMapState;
  mappingStackStatus?: WarehouseMappingStackStatus | null;
}) {
  const pose = state.latestUpdate?.pose;
  const lastChunk = state.chunks.at(-1);
  const stackPhase = mappingStackStatus?.phase ?? "stopped";
  const rows = [
    ["Stream", STATUS_LABELS[state.connectionState]],
    ["Last update", formatTime(state.lastUpdateAt)],
    ["Sequence", String(state.latestUpdate?.changed_chunks?.[0]?.sequence ?? lastChunk?.sequence ?? "--")],
    ["Points (last)", String(lastChunk?.point_count ?? "--")],
    ["Pose X", pose ? `${pose.x_m.toFixed(2)} m` : "--"],
    ["Pose Y", pose ? `${pose.y_m.toFixed(2)} m` : "--"],
    ["Pose Z", pose ? `${pose.z_m.toFixed(2)} m` : "--"],
    ["Nvblox", state.health.nvblox_ready ? "ready" : "off"],
    ["Recording", state.health.mapping_recording ? "yes" : "no"],
    ["Stack", mappingStackStatus?.nvblox_running ? "nvblox running" : stackPhase],
    ["Chunks", String(state.chunks.length)],
    ["Path samples", String(state.scanPath.length)],
  ] as const;

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "repeat(2, minmax(0, 1fr))",
          sm: "repeat(3, minmax(0, 1fr))",
          md: "repeat(4, minmax(0, 1fr))",
        },
        gap: 0.75,
      }}
    >
      {rows.map(([label, value]) => metricRow(label, value))}
    </Box>
  );
}

export function WarehouseLiveVoxelHealthChips({
  state,
}: {
  state: WarehouseLiveVoxelMapState;
}) {
  const badgeColor = (value: boolean): "success" | "warning" =>
    value ? "success" : "warning";
  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap">
      <Chip
        size="small"
        color={badgeColor(state.health.nvblox_ready)}
        label={state.health.nvblox_ready ? "nvblox ready" : "nvblox off"}
      />
      <Chip
        size="small"
        color={badgeColor(state.health.mapping_recording)}
        label={
          state.health.mapping_recording ? "recording" : "not recording"
        }
      />
      <Chip
        size="small"
        color={badgeColor(state.health.stack_running)}
        label={state.health.stack_running ? "stack up" : "stack down"}
      />
      <Tooltip title="Estimated scanned surface coverage">
        <Chip
          size="small"
          color={state.health.coverage_percent != null ? "success" : "default"}
          label={`coverage ${state.health.coverage_percent?.toFixed(0) ?? "--"}%`}
        />
      </Tooltip>
      <Tooltip title="Estimated localization drift">
        <Chip
          size="small"
          color={
            (state.health.drift_estimate_m ?? 0) > 0.5 ? "warning" : "success"
          }
          label={`drift ${state.health.drift_estimate_m?.toFixed(2) ?? "--"}m`}
        />
      </Tooltip>
      <Tooltip title="Costmap freshness">
        <Chip
          size="small"
          color={state.health.stale_costmap ? "warning" : "success"}
          label={state.health.stale_costmap ? "stale costmap" : "costmap fresh"}
        />
      </Tooltip>
      <Tooltip title="Mesh chunk availability">
        <Chip
          size="small"
          color={badgeColor(!state.health.missing_mesh)}
          label={state.health.missing_mesh ? "missing mesh" : "mesh"}
        />
      </Tooltip>
      <Tooltip title="Point-cloud chunk availability">
        <Chip
          size="small"
          color={badgeColor(!state.health.missing_point_cloud)}
          label={
            state.health.missing_point_cloud
              ? "missing point cloud"
              : "point cloud"
          }
        />
      </Tooltip>
    </Stack>
  );
}

export function WarehouseLiveVoxelOverlay({
  state,
}: {
  state: WarehouseLiveVoxelMapState;
}) {
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
  return (
    <Box
      sx={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        color: "common.white",
        textAlign: "center",
        px: 3,
        pointerEvents: "none",
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
      <Typography variant="caption" sx={{ opacity: 0.72 }}>
        {body}
      </Typography>
    </Box>
  );
}
