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
        <Typography variant="subtitle1">Live Voxel Map</Typography>
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

export function WarehouseLiveVoxelHealthChips({
  state,
}: {
  state: WarehouseLiveVoxelMapState;
}) {
  const badgeColor = (value: boolean): "success" | "warning" =>
    value ? "success" : "warning";
  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap">
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
