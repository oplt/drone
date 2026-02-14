import { useMemo } from "react";
import {
  Box,
  Grid,
  Stack,
  Typography,
  Paper,
  Chip,
  Divider,
  LinearProgress,
} from "@mui/material";
import Header from "../components/Header";
import CustomizedDataGrid from "../components/CustomizedDataGrid";
import useAnalyticsOverview from "../../../hooks/useAnalyticsOverview";
import useTelemetryWebSocket from "../../../hooks/useTelemetryWebsocket";

const formatDuration = (minutes: number | null | undefined) => {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return "--";
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h}h ${m}m`;
};

const formatTime = (iso?: string | null) => {
  if (!iso) return "--";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "--";
  return dt.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
};

export default function FleetPage() {
  const { data, loading } = useAnalyticsOverview();
  const wsEnabled = Boolean(data?.system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });
  const system = data?.system;

  const recentRows = useMemo(() => {
    if (!data?.recent_flights) return [];
    return data.recent_flights.map((flight) => ({
      id: flight.id,
      plan: flight.name,
      status:
        flight.status === "in_progress"
          ? "Active"
          : flight.status === "failed"
            ? "Failed"
            : "Completed",
      duration: formatDuration(flight.duration_min),
      distance: `${flight.distance_km.toFixed(1)} km`,
      telemetry_points: flight.telemetry_points,
      started_at: formatTime(flight.started_at),
    }));
  }, [data?.recent_flights]);

  const linkQualityRaw = telemetry?.link?.telemetry ?? telemetry?.link?.rc ?? null;
  const windSpeedRaw = telemetry?.wind?.speed ?? null;
  const batteryPctRaw = telemetry?.battery?.remaining ?? null;
  const linkQuality =
    typeof linkQualityRaw === "number" ? linkQualityRaw : Number(linkQualityRaw);
  const windSpeed =
    typeof windSpeedRaw === "number" ? windSpeedRaw : Number(windSpeedRaw);
  const batteryPctCandidate =
    typeof batteryPctRaw === "number" ? batteryPctRaw : Number(batteryPctRaw);
  const batteryPct =
    Number.isFinite(batteryPctCandidate) && batteryPctCandidate >= 0
      ? batteryPctCandidate
      : null;

  return (
    <>
      <Header />
      <Box sx={{ width: "100%", maxWidth: 1400, p: 2 }}>
        <Stack spacing={3}>
          <Stack spacing={1}>
            <Typography variant="h4">Fleet Control</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Monitor fleet connectivity, live link quality, and active flight status.
            </Typography>
          </Stack>

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, lg: 4 }}>
              <Paper
                variant="outlined"
                sx={{
                  p: 3,
                  borderRadius: 3,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                  height: "100%",
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="h6">System link</Typography>
                  <Chip
                    size="small"
                    label={isConnected ? "Live" : "Offline"}
                    color={isConnected ? "success" : "default"}
                  />
                </Stack>
                <Divider sx={{ my: 2 }} />
                <Stack spacing={2}>
                  <Box>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary">
                        Link quality
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {Number.isFinite(linkQuality) ? `${Math.round(linkQuality)}%` : "--"}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={Number.isFinite(linkQuality) ? linkQuality : 0}
                      sx={{ height: 6, borderRadius: 999 }}
                    />
                  </Box>
                  <Box>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary">
                        Wind @ altitude
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {Number.isFinite(windSpeed) ? `${windSpeed.toFixed(1)} m/s` : "--"}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={
                        Number.isFinite(windSpeed)
                          ? Math.min(100, windSpeed * 8)
                          : 0
                      }
                      sx={{ height: 6, borderRadius: 999 }}
                    />
                  </Box>
                  <Box>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary">
                        Battery reserve
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {batteryPct !== null ? `${Math.round(batteryPct)}%` : "--"}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={batteryPct ?? 0}
                      color={
                        batteryPct !== null && batteryPct < 30
                          ? "error"
                          : "primary"
                      }
                      sx={{ height: 6, borderRadius: 999 }}
                    />
                  </Box>
                  <Divider />
                  <Stack spacing={1}>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary">
                        Telemetry stream
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {system?.telemetry_running ? "Running" : "Stopped"}
                      </Typography>
                    </Stack>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary">
                        MAVLink
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {system?.mavlink_connected ? "Connected" : "Idle"}
                      </Typography>
                    </Stack>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary">
                        Active clients
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {system?.active_connections ?? 0}
                      </Typography>
                    </Stack>
                  </Stack>
                </Stack>
              </Paper>
            </Grid>
            <Grid size={{ xs: 12, lg: 8 }}>
              <Paper
                variant="outlined"
                sx={{
                  p: 3,
                  borderRadius: 3,
                  borderColor: "hsla(174, 30%, 40%, 0.25)",
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="h6">Recent flights</Typography>
                  <Chip
                    size="small"
                    label={`${data?.recent_flights?.length ?? 0} flights`}
                  />
                </Stack>
                <Divider sx={{ my: 2 }} />
                <CustomizedDataGrid rows={recentRows} loading={loading} />
              </Paper>
            </Grid>
          </Grid>
        </Stack>
      </Box>
    </>
  );
}
