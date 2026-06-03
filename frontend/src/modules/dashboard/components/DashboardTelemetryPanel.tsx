import Grid from "@mui/material/Grid";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { PageSection } from "../../../shared/layout/PageLayout";

type DashboardTelemetryPanelProps = {
  isConnected: boolean;
  mode: string;
  altitudeM: number;
  speedMps: number;
  batteryPct: number | null;
  satellites: number;
  hdop: number;
};

const metricMeta = {
  mode: "Current autopilot mode reported by telemetry.",
  altitude: "Relative altitude above launch/home point.",
  speed: "Current ground speed in meters per second.",
  battery: "Remaining battery percentage from latest telemetry.",
};

function MiniMetric({
  label,
  value,
  tooltip,
}: {
  label: string;
  value: string;
  tooltip: string;
}) {
  return (
    <Tooltip title={tooltip} arrow>
      <Stack spacing={0.25}>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h6" sx={{ lineHeight: 1.1 }}>
          {value}
        </Typography>
      </Stack>
    </Tooltip>
  );
}

export default function DashboardTelemetryPanel({
  isConnected,
  mode,
  altitudeM,
  speedMps,
  batteryPct,
  satellites,
  hdop,
}: DashboardTelemetryPanelProps) {
  const gpsValue = Number.isFinite(satellites)
    ? Math.min(100, satellites * 8)
    : 0;

  return (
    <PageSection
      title="Live telemetry"
      description="Compact vehicle health snapshot."
      sx={{ height: "100%" }}
      action={
        <Tooltip title="WebSocket telemetry stream state" arrow>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              color: isConnected ? "success.main" : "text.secondary",
            }}
          >
            {isConnected ? "LIVE" : "OFFLINE"}
          </Typography>
        </Tooltip>
      }
    >
      <Stack spacing={2}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 6, md: 3 }}>
            <MiniMetric label="Mode" value={mode} tooltip={metricMeta.mode} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <MiniMetric
              label="Altitude"
              value={
                Number.isFinite(altitudeM) ? `${altitudeM.toFixed(1)} m` : "--"
              }
              tooltip={metricMeta.altitude}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <MiniMetric
              label="Speed"
              value={
                Number.isFinite(speedMps) ? `${speedMps.toFixed(1)} m/s` : "--"
              }
              tooltip={metricMeta.speed}
            />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <MiniMetric
              label="Battery"
              value={batteryPct !== null ? `${Math.round(batteryPct)}%` : "--"}
              tooltip={metricMeta.battery}
            />
          </Grid>
        </Grid>

        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <Tooltip
            title="GPS quality estimate based on visible satellites and HDOP."
            arrow
          >
            <Stack sx={{ flex: 1 }} spacing={0.75}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  GPS
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  {Number.isFinite(satellites) ? satellites : "--"} sats / HDOP{" "}
                  {Number.isFinite(hdop) ? hdop.toFixed(1) : "--"}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={gpsValue}
                sx={{ height: 6, borderRadius: 999 }}
              />
            </Stack>
          </Tooltip>
          <Tooltip title="Battery reserve from latest telemetry frame." arrow>
            <Stack sx={{ flex: 1 }} spacing={0.75}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  Battery
                </Typography>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  {batteryPct !== null ? `${Math.round(batteryPct)}%` : "--"}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={batteryPct ?? 0}
                color={
                  batteryPct !== null && batteryPct < 30 ? "error" : "primary"
                }
                sx={{ height: 6, borderRadius: 999 }}
              />
            </Stack>
          </Tooltip>
        </Stack>
      </Stack>
    </PageSection>
  );
}
