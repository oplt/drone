import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import HighlightOffRoundedIcon from "@mui/icons-material/HighlightOffRounded";
import PendingRoundedIcon from "@mui/icons-material/PendingRounded";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";

const CHECK_LABELS: Record<string, string> = {
  bridge: "Bridge / ROS link",
  gazebo: "Gazebo sensors",
  sensors: "RGB / depth / IMU",
  odometry: "Local odometry",
  localization: "SLAM / localization",
  tf: "TF tree",
  nvblox: "Nvblox (starts at flight)",
  stability: "Perception stability",
  vehicle_link: "Drone link",
  telemetry_stream: "Telemetry stream",
  battery: "Battery",
  planner: "Mission planner",
  failsafe: "Failsafe",
};

function statusIcon(value: string) {
  if (value === "OK") return <CheckCircleOutlineRoundedIcon fontSize="small" color="success" />;
  if (value === "FAIL") return <HighlightOffRoundedIcon fontSize="small" color="error" />;
  if (value === "WARN") return <PendingRoundedIcon fontSize="small" color="warning" />;
  return <PendingRoundedIcon fontSize="small" color="warning" />;
}

function statusLabel(value: string) {
  if (value === "OK") return "PASS";
  if (value === "FAIL") return "FAIL";
  if (value === "WARN") return "WARN";
  if (value === "DEFERRED") return "DEFERRED";
  if (value === "WAITING") return "WAITING";
  return value;
}

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
  const requiredMs = preflight?.perception_required_stable_ms ?? 8000;
  const stableMs = preflight?.perception_stable_for_ms ?? 0;
  const stabilityProgress =
    requiredMs > 0 ? Math.min(100, (stableMs / requiredMs) * 100) : 0;

  const categories = preflight?.categories ?? {};
  const checkEntries = Object.entries(categories);

  return (
    <Box sx={{ p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <Stack spacing={1.25}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle2">Warehouse Preflight</Typography>
          {preflight && (
            <Chip
              size="small"
              label={preflight.ready_to_fly ? "PASSED" : "NOT READY"}
              color={preflight.ready_to_fly ? "success" : "warning"}
            />
          )}
        </Stack>

        <Typography variant="body2" color="text.secondary">
          Run checks when Gazebo is playing and ROS sensors are up. Includes vehicle link,
          MAVLink telemetry, battery, and perception stability (~
          {Math.round(requiredMs / 1000)}s) before flight controls unlock.
        </Typography>

        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Button variant="contained" size="small" disabled={running} onClick={onRunChecks}>
            {running ? "Running checks…" : preflight ? "Re-run preflight checks" : "Run preflight checks"}
          </Button>
          {flightAvailable && onOpenFlight && (
            <Button variant="outlined" size="small" color="primary" onClick={onOpenFlight}>
              Open flight
            </Button>
          )}
        </Stack>

        {running && <LinearProgress />}

        {preflight && (
          <Stack spacing={0.5}>
            <Typography variant="caption" color="text.secondary">
              Stability {stableMs}ms / {requiredMs}ms
            </Typography>
            <LinearProgress variant="determinate" value={stabilityProgress} />
          </Stack>
        )}

        {checkEntries.length > 0 && (
          <Stack spacing={0.75}>
            {checkEntries.map(([key, value]) => (
              <Stack
                key={key}
                direction="row"
                spacing={1}
                alignItems="center"
                sx={{
                  px: 1,
                  py: 0.75,
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "divider",
                }}
              >
                {statusIcon(value)}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2">{CHECK_LABELS[key] ?? key}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {statusLabel(value)}
                  </Typography>
                </Box>
              </Stack>
            ))}
          </Stack>
        )}

        {preflight?.blocking_reasons?.length ? (
          <Alert severity="warning" sx={{ py: 0.25 }}>
            <Stack spacing={0.25}>
              {preflight.blocking_reasons.map((reason) => (
                <Typography key={reason} variant="body2">
                  {reason}
                </Typography>
              ))}
            </Stack>
          </Alert>
        ) : null}

        {error && (
          <Alert severity="error" sx={{ py: 0.25 }}>
            {error}
          </Alert>
        )}

        {preflight?.note && (
          <Typography variant="caption" color="text.secondary">
            {preflight.note}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}
