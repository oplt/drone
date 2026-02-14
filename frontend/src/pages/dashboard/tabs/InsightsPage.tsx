import { useMemo } from "react";
import {
  Box,
  Grid,
  Stack,
  Typography,
  Paper,
  Chip,
  Divider,
  Alert,
} from "@mui/material";
import Header from "../components/Header";
import useAnalyticsOverview from "../../../hooks/useAnalyticsOverview";
import useTelemetryWebSocket from "../../../hooks/useTelemetryWebsocket";
import SessionsChart from "../components/SessionsChart";
import PageViewsBarChart from "../components/PageViewsBarChart";
import ChartUserByCountry from "../components/ChartUserByCountry";

const formatDateLabel = (iso: string) => {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

const formatNumber = (value: number | null | undefined, suffix = "") => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${value.toLocaleString()}${suffix}`;
};

const formatHours = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${value.toFixed(1)}h`;
};

const deltaLabelFromSeries = (series: number[]) => {
  if (series.length < 2) return undefined;
  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  if (!Number.isFinite(last) || !Number.isFinite(prev) || prev === 0) return undefined;
  const pct = ((last - prev) / Math.abs(prev)) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
};

export default function InsightsPage() {
  const { data, loading, error } = useAnalyticsOverview();
  const wsEnabled = Boolean(data?.system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });

  const labels = useMemo(
    () => (data?.trends?.days ?? []).map(formatDateLabel),
    [data?.trends?.days],
  );
  const flightCounts = data?.trends?.flight_counts ?? [];
  const telemetryCounts = data?.trends?.telemetry_counts ?? [];
  const flightHours = data?.trends?.flight_hours ?? [];
  const hasHoursData = flightHours.length > 0;
  const hasActivityData = flightCounts.length > 0 || telemetryCounts.length > 0;
  const hoursDelta = deltaLabelFromSeries(flightHours);
  const activityDelta = deltaLabelFromSeries(flightCounts);

  const windSpeedRaw = telemetry?.wind?.speed ?? null;
  const linkQualityRaw =
    telemetry?.link?.telemetry ?? telemetry?.link?.rc ?? null;
  const batteryPctRaw = telemetry?.battery?.remaining ?? null;
  const windSpeed =
    typeof windSpeedRaw === "number" ? windSpeedRaw : Number(windSpeedRaw);
  const linkQuality =
    typeof linkQualityRaw === "number" ? linkQualityRaw : Number(linkQualityRaw);
  const batteryPctCandidate =
    typeof batteryPctRaw === "number" ? batteryPctRaw : Number(batteryPctRaw);
  const batteryPct =
    Number.isFinite(batteryPctCandidate) && batteryPctCandidate >= 0
      ? batteryPctCandidate
      : null;

  const recommendations = [
    Number.isFinite(windSpeed) && windSpeed > 8
      ? "High wind at altitude. Consider rescheduling sensitive flights."
      : null,
    batteryPct !== null && batteryPct < 35
      ? "Battery reserve below target. Plan shorter routes."
      : null,
    Number.isFinite(linkQuality) && linkQuality < 50
      ? "Link quality degraded. Verify uplink and ground station positioning."
      : null,
  ].filter(Boolean) as string[];

  return (
    <>
      <Header />
      <Box sx={{ width: "100%", maxWidth: 1400, p: 2 }}>
        <Stack spacing={3}>
          <Stack spacing={1}>
            <Typography variant="h4">Field Insights</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Trends, alerts, and agronomy-ready signals based on flight history and
              live telemetry.
            </Typography>
            {error && (
              <Alert severity="warning">
                {error}
              </Alert>
            )}
          </Stack>

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, lg: 8 }}>
              <SessionsChart
                title="Survey hours trend"
                totalValue={formatHours(data?.summary?.flight_hours_7d)}
                deltaLabel={hoursDelta}
                subtitle="Flight hours per day for the last 30 days"
                labels={hasHoursData ? labels : undefined}
                series={
                  hasHoursData
                    ? [
                        {
                          id: "hours",
                          label: "Hours",
                          data: flightHours,
                        },
                      ]
                    : undefined
                }
              />
            </Grid>
            <Grid size={{ xs: 12, lg: 4 }}>
              <ChartUserByCountry
                segments={data?.coverage}
                totalLabel="Coverage segments"
              />
            </Grid>
          </Grid>

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>
              <PageViewsBarChart
                title="Activity mix"
                totalValue={formatNumber(data?.summary?.flights_24h)}
                deltaLabel={activityDelta}
                subtitle="Flights and telemetry points for the last 7 days"
                labels={hasActivityData ? labels.slice(-7) : undefined}
                series={
                  hasActivityData
                    ? [
                        { id: "flights", label: "Flights", data: flightCounts.slice(-7) },
                        {
                          id: "telemetry",
                          label: "Telemetry",
                          data: telemetryCounts.slice(-7),
                        },
                      ]
                    : undefined
                }
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
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
                  <Typography variant="h6">Recommendations</Typography>
                  <Chip
                    size="small"
                    label={isConnected ? "Live telemetry" : "Telemetry offline"}
                    color={isConnected ? "success" : "default"}
                  />
                </Stack>
                <Divider sx={{ my: 2 }} />
                {loading ? (
                  <Typography variant="body2" color="text.secondary">
                    Loading recommendations...
                  </Typography>
                ) : recommendations.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No critical recommendations. Operations within optimal bounds.
                  </Typography>
                ) : (
                  <Stack spacing={1.5}>
                    {recommendations.map((item) => (
                      <Alert key={item} severity="info">
                        {item}
                      </Alert>
                    ))}
                  </Stack>
                )}
              </Paper>
            </Grid>
          </Grid>

          <Paper
            variant="outlined"
            sx={{
              p: 3,
              borderRadius: 3,
              borderColor: "hsla(174, 30%, 40%, 0.25)",
            }}
          >
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6">Recent events</Typography>
              <Chip size="small" label={`${data?.events?.length ?? 0} events`} />
            </Stack>
            <Divider sx={{ my: 2 }} />
            {data?.events && data.events.length > 0 ? (
              <Stack spacing={1.5}>
                {data.events.map((evt) => (
                  <Box key={evt.id} sx={{ display: "flex", gap: 2 }}>
                    <Chip size="small" label={evt.type} color="warning" />
                    <Stack>
                      <Typography variant="body2">
                        Flight #{evt.flight_id} • {new Date(evt.created_at).toLocaleString()}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {JSON.stringify(evt.data)}
                      </Typography>
                    </Stack>
                  </Box>
                ))}
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No events recorded in the current window.
              </Typography>
            )}
          </Paper>
        </Stack>
      </Box>
    </>
  );
}
