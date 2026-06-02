import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import HighlightOffRoundedIcon from "@mui/icons-material/HighlightOffRounded";
import PendingRoundedIcon from "@mui/icons-material/PendingRounded";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";

const CHECK_LABELS: Record<string, string> = {
  bridge: "Bridge / ROS link",
  gazebo: "Gazebo sensors",
  rgb_depth_imu: "RGB / depth / IMU",
  lidar: "Raw lidar",
  sensors: "Core sensors",
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

const TOPIC_LABELS: Record<string, string> = {
  raw_lidar: "Raw lidar",
  rgb_image: "RGB camera",
  depth: "Depth camera",
  imu: "IMU",
  visual_slam_odom: "Local odometry",
  lidar_scan: "Raw lidar scan",
  lidar_points: "Raw lidar points",
};

function topicLabel(value: string) {
  return TOPIC_LABELS[value] ?? value;
}

function statusIcon(value: string) {
  if (value === "OK")
    return <CheckCircleOutlineRoundedIcon fontSize="small" color="success" />;
  if (value === "FAIL")
    return <HighlightOffRoundedIcon fontSize="small" color="error" />;
  if (value === "WARN")
    return <PendingRoundedIcon fontSize="small" color="warning" />;
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
  const requiredMissing = preflight?.diagnostics?.topics?.required_missing ?? [];
  const requiredUnhealthy =
    preflight?.diagnostics?.topics?.required_unhealthy ?? [];
  const deferredMissing = preflight?.diagnostics?.topics?.deferred_missing ?? [];
  const stabilityRemainingMs =
    preflight?.diagnostics?.stability?.remaining_ms ??
    Math.max(0, requiredMs - stableMs);
  const stabilityResetReason =
    preflight?.diagnostics?.stability?.last_reset_reason;
  const topicCategories = preflight?.diagnostics?.topics?.by_category ?? {};

  return (
    <Box
      sx={{
        p: 1.25,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
      }}
    >
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

        <Typography variant="caption" color="text.secondary">
          Polls telemetry, ROS, battery, and perception stability (~
          {Math.round(requiredMs / 1000)}s).
        </Typography>

        {preflight && !preflight.bridge_ok && (
          <Alert severity="error" sx={{ py: 0.25 }}>
            <Stack
              spacing={0.5}
              direction="row"
              alignItems="center"
              flexWrap="wrap"
            >
              <Typography variant="body2">ROS stack unreachable.</Typography>
              {preflight.warehouse_bridge_state && (
                <Chip
                  size="small"
                  label={`Bridge ${preflight.warehouse_bridge_state}`}
                  color="error"
                />
              )}
              {preflight.restart_count != null &&
                preflight.restart_count > 0 && (
                  <Chip
                    size="small"
                    label={`Restarts ${preflight.restart_count}`}
                  />
                )}
              <Tooltip title="Start Gazebo with Play/gz sim -r, gazebo_sensor_bridge, warehouse_bridge on port 8088, warehouse_sim_tf, and warehouse_odometry_export.">
                <Chip size="small" label="Startup steps" variant="outlined" />
              </Tooltip>
              {preflight.ros_topic_count != null && (
                <Chip
                  size="small"
                  label={`${preflight.ros_topic_count} ROS topics`}
                />
              )}
            </Stack>
            {preflight.last_error && (
              <Typography variant="caption" color="error">
                {preflight.last_error}
              </Typography>
            )}
          </Alert>
        )}

        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Button
            variant="contained"
            size="small"
            disabled={running}
            onClick={onRunChecks}
          >
            {running
              ? "Running checks…"
              : preflight
                ? "Re-run preflight checks"
                : "Run preflight checks"}
          </Button>
          {flightAvailable && onOpenFlight && (
            <Button
              variant="outlined"
              size="small"
              color="primary"
              onClick={onOpenFlight}
            >
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
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: {
                xs: "1fr",
                sm: "repeat(2, minmax(0, 1fr))",
              },
              gap: 0.75,
            }}
          >
            {checkEntries.map(([key, value]) => (
              <Stack
                key={key}
                direction="row"
                spacing={1}
                alignItems="center"
                sx={{
                  px: 1,
                  py: 0.5,
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "divider",
                  minWidth: 0,
                }}
              >
                {statusIcon(value)}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2">
                    {CHECK_LABELS[key] ?? key}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {statusLabel(value)}
                  </Typography>
                </Box>
              </Stack>
            ))}
          </Box>
        )}

        {preflight?.blocking_reasons?.length ? (
          <Stack spacing={0.5}>
            {preflight.blocking_reasons.map((reason, index) => (
              <Accordion
                key={reason}
                disableGutters
                elevation={0}
                sx={{ border: "1px solid", borderColor: "divider" }}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreRoundedIcon fontSize="small" />}
                >
                  <Stack
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    sx={{ minWidth: 0 }}
                  >
                    <Chip
                      size="small"
                      color="warning"
                      label={`Blocker ${index + 1}`}
                    />
                    <Typography variant="body2" noWrap>
                      {reason}
                    </Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="body2" color="text.secondary">
                    Resolve this blocker, then re-run preflight. Startup
                    commands and ROS topic details are available from the setup
                    tooltips and bridge health panel.
                  </Typography>
                </AccordionDetails>
              </Accordion>
            ))}
          </Stack>
        ) : null}

        {preflight?.suggested_actions?.length ? (
          <Alert severity="info" sx={{ py: 0.25 }}>
            <Stack spacing={0.5}>
              {preflight.suggested_actions.map((action) => (
                <Typography key={action} variant="caption">
                  {action}
                </Typography>
              ))}
            </Stack>
          </Alert>
        ) : null}

        {preflight && (requiredMissing.length || requiredUnhealthy.length || deferredMissing.length) ? (
          <Stack spacing={0.5}>
            {requiredMissing.length ? (
              <Typography variant="caption" color="error">
                Missing required topics: {requiredMissing.map(topicLabel).join(", ")}
              </Typography>
            ) : null}
            {requiredUnhealthy.length ? (
              <Typography variant="caption" color="error">
                Unhealthy required topics: {requiredUnhealthy.map(topicLabel).join(", ")}
              </Typography>
            ) : null}
            {deferredMissing.length ? (
              <Typography variant="caption" color="text.secondary">
                Deferred nvblox topics: {deferredMissing.join(", ")}
              </Typography>
            ) : null}
          </Stack>
        ) : null}

        {Object.keys(topicCategories).length ? (
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: {
                xs: "1fr",
                sm: "repeat(2, minmax(0, 1fr))",
              },
              gap: 0.5,
            }}
          >
            {Object.entries(topicCategories).map(([key, topic]) => (
              <Typography key={key} variant="caption" color="text.secondary">
                {topicLabel(key)}: {statusLabel(topic.status ?? "UNKNOWN")}
                {topic.topic ? ` · ${topic.topic}` : ""}
              </Typography>
            ))}
          </Box>
        ) : null}

        {preflight && !preflight.stability_ok ? (
          <Typography variant="caption" color="text.secondary">
            Stability remaining {stabilityRemainingMs}ms
            {stabilityResetReason ? ` · ${stabilityResetReason}` : ""}
          </Typography>
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
