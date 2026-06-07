import {
  Box,
  Button,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import { WarehouseStatusBadge } from "./WarehouseStatusBadge";
import { PreflightGroup } from "./WarehousePreflightRows";
import {
  buildPreflightGroups,
  preflightProgress,
  readinessStatus,
  strongestPreflightBlocker,
} from "./warehousePreflightViewModel";

type Props = {
  preflight: WarehouseGoPreflight | null;
  running?: boolean;
  error?: string | null;
  onRunChecks: () => void;
  onOpenFlight?: () => void;
  flightAvailable?: boolean;
};

export function WarehousePreflightChecksPanel({
  preflight,
  running = false,
  error,
  onRunChecks,
  onOpenFlight,
  flightAvailable = false,
}: Props) {
  const { passed, total } = preflightProgress(preflight);
  const groups = buildPreflightGroups(preflight);
  const status = readinessStatus(preflight, running);
  const stableMs = preflight?.perception_stable_for_ms ?? 0;
  const requiredMs = preflight?.perception_required_stable_ms ?? 8000;
  const progress = total > 0 ? (passed / total) * 100 : 0;
  const blocker = strongestPreflightBlocker(preflight, running);
  const diagnosticsAgeMs = preflight?.diagnostics_age_ms;
  const staleWarnMs =
    preflight?.diagnostics?.freshness?.stale_warn_threshold_ms ??
    preflight?.diagnostics?.bridge?.health_sample_max_age_ms ??
    8000;
  const diagnosticsStale =
    typeof diagnosticsAgeMs === "number" && diagnosticsAgeMs > staleWarnMs;
  const refreshInProgress = Boolean(
    preflight?.diagnostics?.cache?.refresh_in_progress ||
      preflight?.diagnostics?.timings?.refresh_in_progress ||
      preflight?.diagnostics?.bridge?.health_probe_in_progress,
  );
  const bridgeWarming =
    preflight?.warehouse_bridge_state === "starting" ||
    preflight?.warehouse_bridge_state === "process_running";
  const preflightBusy = running || refreshInProgress || bridgeWarming;

  return (
    <Stack spacing={1.5}>
      <Box
        sx={{
          p: 1.75,
          borderRadius: 3,
          bgcolor:
            status === "blocked"
              ? "error.main"
              : status === "ready"
                ? "success.main"
                : "warning.main",
          color: status === "unknown" ? "text.primary" : "common.white",
        }}
      >
        <Stack spacing={1}>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            spacing={1}
          >
            <Typography
              variant="h6"
              sx={{ fontWeight: 800, fontSize: "1.1rem" }}
            >
              {preflight?.ready_to_fly ? "Ready to fly" : "Not ready to fly"}
            </Typography>
            <WarehouseStatusBadge status={status} />
          </Stack>
          <Typography variant="body2" sx={{ fontWeight: 750 }}>
            Primary blocker: {blocker}
          </Typography>
          <Typography variant="caption" sx={{ opacity: 0.9 }}>
            Ready to fly: {preflight?.ready_to_fly ? "YES" : "NO"}
          </Typography>
          <Typography variant="caption" sx={{ opacity: 0.9 }}>
            Waiting for ROS bridge, source transport sensors, and telemetry stability.
          </Typography>
        </Stack>
      </Box>

      <Box
        sx={{
          p: 1.25,
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <Stack spacing={0.75}>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
          >
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {passed} / {total} checks passed
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ fontFamily: "monospace" }}
            >
              {stableMs}ms / {requiredMs}ms stable
            </Typography>
          </Stack>
          <LinearProgress
            variant={running ? "indeterminate" : "determinate"}
            value={progress}
          />
        </Stack>
      </Box>

      <Stack direction="row" spacing={1} flexWrap="wrap">
        <Button
          variant="contained"
          size="small"
          disabled={preflightBusy}
          onClick={onRunChecks}
        >
          {preflightBusy
            ? "Running checks..."
            : preflight
              ? "Run preflight checks"
              : "Run preflight checks"}
        </Button>
        <Tooltip title="Start simulation, warehouse_source_transport_bridge, warehouse_bridge on port 8088, warehouse_sim_tf, and warehouse_odometry_export.">
          <Button variant="outlined" size="small">
            Startup steps
          </Button>
        </Tooltip>
        {flightAvailable && onOpenFlight ? (
          <Button variant="text" size="small" onClick={onOpenFlight}>
            View diagnostics
          </Button>
        ) : (
          <Button variant="text" size="small" disabled>
            View diagnostics
          </Button>
        )}
      </Stack>

      {error ? (
        <Box
          sx={{
            p: 1.25,
            borderRadius: 2,
            bgcolor: "error.main",
            color: "common.white",
          }}
        >
          <Typography variant="body2">{error}</Typography>
        </Box>
      ) : null}

      {diagnosticsStale ? (
        <Typography variant="caption" color="warning.main">
          Diagnostics sample stale ({diagnosticsAgeMs}ms old; refresh threshold{" "}
          {staleWarnMs}ms).
        </Typography>
      ) : null}

      {groups.map((group) => (
        <PreflightGroup
          key={group.title}
          title={group.title}
          checks={group.checks}
        />
      ))}

      {preflight?.suggested_actions?.length ? (
        <Box
          sx={{
            p: 1.25,
            borderRadius: 2,
            bgcolor: "info.main",
            color: "common.white",
          }}
        >
          {preflight.suggested_actions.slice(0, 3).map((action) => (
            <Typography key={action} variant="caption" display="block">
              {action}
            </Typography>
          ))}
        </Box>
      ) : null}
    </Stack>
  );
}
