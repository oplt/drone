import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import type {
  WarehouseFlightReadiness,
  WarehouseFlightSubsystemStatus,
} from "../api/warehouseFlightApi";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";

function statusColor(
  status: WarehouseFlightSubsystemStatus | string | undefined,
): "success" | "warning" | "error" | "default" {
  switch (status) {
    case "OK":
      return "success";
    case "WARN":
      return "warning";
    case "FAIL":
      return "error";
    case "WAITING":
      return "default";
    default:
      return "default";
  }
}

const SUBSYSTEM_ORDER = [
  "bridge",
  "autopilot",
  "sensors",
  "slam",
  "nvblox",
  "planner",
  "failsafe",
] as const;

const SUBSYSTEM_LABELS: Record<string, string> = {
  bridge: "Bridge",
  autopilot: "Autopilot",
  sensors: "Sensors",
  slam: "SLAM",
  nvblox: "Nvblox",
  planner: "Planner",
  failsafe: "Failsafe",
};

function readinessChipLabel(label: string, status: string): string {
  return `${label} ${status}`;
}

type Props = {
  readiness?: WarehouseFlightReadiness | null;
  preflight?: WarehouseGoPreflight | null;
  loading?: boolean;
  onStart?: () => void;
  starting?: boolean;
  startDisabled?: boolean;
  startDisabledReason?: string;
  onPause?: () => void;
  onAbort?: () => void;
  onLand?: () => void;
  commandBusy?: boolean;
  showControls?: boolean;
};

export function WarehouseFlightReadinessPanel({
  readiness,
  preflight,
  loading = false,
  onStart,
  starting = false,
  startDisabled = false,
  startDisabledReason,
  onPause,
  onAbort,
  onLand,
  commandBusy = false,
  showControls = false,
}: Props) {
  if (loading && !readiness && !preflight) {
    return (
      <Box sx={{ mt: 2, p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
        <LinearProgress />
      </Box>
    );
  }
  if (!readiness && !preflight) return null;

  const canStart =
    preflight?.ready_to_fly === true || readiness?.ready_to_takeoff === true;
  const blockingReasons =
    (preflight?.blocking_reasons?.length ? preflight.blocking_reasons : null) ??
    readiness?.blocking_reasons ??
    [];
  const perceptionRequiredMs =
    preflight?.perception_required_stable_ms ??
    readiness?.perception_required_stable_ms ??
    8000;
  const perceptionStableMs =
    preflight?.perception_stable_for_ms ?? readiness?.perception_stable_for_ms ?? 0;
  const perceptionProgress =
    perceptionRequiredMs > 0
      ? Math.min(100, (perceptionStableMs / perceptionRequiredMs) * 100)
      : 0;

  const categoryChips = preflight?.categories
    ? Object.entries(preflight.categories).map(([key, value]) => ({
        key,
        label: `${key}: ${value}`,
        color: statusColor(
          value === "OK"
            ? "OK"
            : value === "WAITING" || value === "DEFERRED"
              ? "WAITING"
              : value === "FAIL"
                ? "FAIL"
                : "UNKNOWN",
        ),
      }))
    : [];

  if (!readiness) {
    return (
      <Box sx={{ mt: 2, p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
        <Stack spacing={1.25}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
            <Typography variant="subtitle2">Warehouse Preflight</Typography>
            <Chip
              size="small"
              label={preflight?.ready_to_fly ? "READY" : "NOT READY"}
              color={preflight?.ready_to_fly ? "success" : "warning"}
            />
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap">
            {categoryChips.map((chip) => (
              <Tooltip key={chip.key} title={chip.label}>
                <Chip size="small" label={chip.label} color={chip.color} variant="outlined" />
              </Tooltip>
            ))}
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Perception stability {perceptionStableMs}ms / {perceptionRequiredMs}ms
          </Typography>
          <LinearProgress variant="determinate" value={perceptionProgress} />
          {blockingReasons.length > 0 && (
            <Alert severity="warning" sx={{ py: 0.25 }}>
              <Stack spacing={0.25}>
                {blockingReasons.map((reason) => (
                  <Typography key={reason} variant="body2">
                    {reason}
                  </Typography>
                ))}
              </Stack>
            </Alert>
          )}
          {preflight?.note && (
            <Typography variant="caption" color="text.secondary">
              {preflight.note}
            </Typography>
          )}
          {onStart && (
            <Button
              variant="contained"
              size="small"
              disabled={!canStart || startDisabled || starting}
              title={startDisabledReason}
              onClick={onStart}
            >
              Start Warehouse Flight
            </Button>
          )}
        </Stack>
      </Box>
    );
  }

  const slamProgress =
    readiness.slam_required_stable_ms > 0
      ? Math.min(
          100,
          (readiness.slam_stable_for_ms / readiness.slam_required_stable_ms) * 100,
        )
      : 0;
  const perceptionRequiredMsFinal = perceptionRequiredMs;
  const perceptionStableMsFinal = perceptionStableMs;
  const perceptionProgressFinal = perceptionProgress;

  return (
    <Box sx={{ mt: 2, p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <Stack spacing={1.25}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle2">Warehouse Flight Readiness</Typography>
          <Chip size="small" label={readiness.overall_status} color={statusColor(readiness.overall_status)} />
          <Chip size="small" label={readiness.current_state} variant="outlined" />
          {preflight && (
            <Chip
              size="small"
              label={preflight.ready_to_fly ? "Preflight OK" : "Preflight blocked"}
              color={preflight.ready_to_fly ? "success" : "warning"}
              variant="outlined"
            />
          )}
        </Stack>

        {categoryChips.length > 0 && (
          <Stack direction="row" spacing={0.5} flexWrap="wrap">
            {categoryChips.map((chip) => (
              <Chip key={chip.key} size="small" label={chip.label} color={chip.color} variant="outlined" />
            ))}
          </Stack>
        )}

        <Stack direction="row" spacing={0.5} flexWrap="wrap">
          {SUBSYSTEM_ORDER.map((key) => {
            const subsystem = readiness.subsystems[key];
            if (!subsystem) return null;
            return (
              <Tooltip key={key} title={subsystem.message || SUBSYSTEM_LABELS[key]}>
                <Chip
                  size="small"
                  label={readinessChipLabel(SUBSYSTEM_LABELS[key], subsystem.status)}
                  color={statusColor(subsystem.status)}
                  variant="outlined"
                />
              </Tooltip>
            );
          })}
        </Stack>

        <Stack spacing={0.5}>
          <Typography variant="caption" color="text.secondary">
            Perception stability {perceptionStableMsFinal}ms / {perceptionRequiredMsFinal}ms
          </Typography>
          <LinearProgress variant="determinate" value={perceptionProgressFinal} />
          <Typography variant="caption" color="text.secondary">
            SLAM stability {readiness.slam_stable_for_ms}ms / {readiness.slam_required_stable_ms}ms
          </Typography>
          <LinearProgress variant="determinate" value={slamProgress} />
          {readiness.subsystems.nvblox?.costmap_age_ms != null && (
            <Typography variant="caption" color="text.secondary">
              Costmap age {readiness.subsystems.nvblox.costmap_age_ms}ms
            </Typography>
          )}
        </Stack>

        {blockingReasons.length > 0 && (
          <Alert severity="warning" sx={{ py: 0.25 }}>
            <Stack spacing={0.25}>
              {blockingReasons.map((reason) => (
                <Typography key={reason} variant="body2">
                  {reason}
                </Typography>
              ))}
            </Stack>
          </Alert>
        )}

        {preflight?.note && (
          <Typography variant="caption" color="text.secondary">
            {preflight.note}
          </Typography>
        )}

        <Typography variant="caption" color="text.secondary">
          Updated {new Date(readiness.updated_at).toLocaleTimeString()}
          {preflight?.ros_topic_count != null ? ` · ROS topics ${preflight.ros_topic_count}` : ""}
        </Typography>

        {(onStart || showControls) && (
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {onStart && (
              <Button
                variant="contained"
                size="small"
                disabled={!canStart || startDisabled || starting}
                title={startDisabledReason}
                onClick={onStart}
              >
                Start Warehouse Flight
              </Button>
            )}
            {showControls && onPause && (
              <Button variant="outlined" size="small" disabled={commandBusy} onClick={onPause}>
                Pause
              </Button>
            )}
            {showControls && onAbort && (
              <Button variant="outlined" color="warning" size="small" disabled={commandBusy} onClick={onAbort}>
                Abort
              </Button>
            )}
            {showControls && onLand && (
              <Button variant="outlined" color="error" size="small" disabled={commandBusy} onClick={onLand}>
                Land
              </Button>
            )}
          </Stack>
        )}
      </Stack>
    </Box>
  );
}
