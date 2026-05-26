import { Suspense, lazy, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Select from '@mui/material/Select';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Header from "../../../shared/layout/WorkflowHeader";
import PageLayout, { PageSection } from "../../../shared/layout/PageLayout";
import useAnalyticsOverview from "../../../modules/dashboard";
import useTelemetryWebSocket from "../../../modules/mission-runtime";

const SessionsChart = lazy(() => import("../components/SessionsChart"));
const PageViewsBarChart = lazy(() => import("../components/PageViewsBarChart"));
const ChartUserByCountry = lazy(() => import("../components/ChartUserByCountry"));
const FlightReplayChart = lazy(() => import("../components/FlightReplayChart"));

const formatDateLabel = (iso: string) => {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const formatNumber = (value: number | null | undefined, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return `${value.toLocaleString()}${suffix}`;
};

const formatHours = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return `${value.toFixed(1)}h`;
};

const deltaLabelFromSeries = (series: number[]) => {
  if (series.length < 2) return undefined;
  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  if (!Number.isFinite(last) || !Number.isFinite(prev) || prev === 0) return undefined;
  const pct = ((last - prev) / Math.abs(prev)) * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
};

function PanelSkeleton({ height = 300 }: { height?: number }) {
  return (
    <Paper variant="outlined" sx={{ p: 3, borderRadius: 4, minHeight: height }}>
      <Stack spacing={2}>
        <Skeleton variant="rounded" width="34%" height={24} />
        <Skeleton variant="rounded" width="100%" height={height - 60} />
      </Stack>
    </Paper>
  );
}

function formatEventData(data: Record<string, unknown>) {
  const raw = JSON.stringify(data);
  return raw.length > 140 ? `${raw.slice(0, 137)}...` : raw;
}

export default function InsightsPage() {
  const { data, loading, error } = useAnalyticsOverview();
  const wsEnabled = Boolean(data?.system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });

  const recentFlights = data?.recent_flights ?? [];
  const [selectedFlightId, setSelectedFlightId] = useState<number | null>(null);
  // Default to the most recent flight when data loads.
  const activeFlightId =
    selectedFlightId ?? (recentFlights.length > 0 ? recentFlights[0].id : null);

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
  const linkQualityRaw = telemetry?.link?.telemetry ?? telemetry?.link?.rc ?? null;
  const batteryPctRaw = telemetry?.battery?.remaining ?? null;
  const windSpeed = typeof windSpeedRaw === 'number' ? windSpeedRaw : Number(windSpeedRaw);
  const linkQuality =
    typeof linkQualityRaw === 'number' ? linkQualityRaw : Number(linkQualityRaw);
  const batteryPctCandidate =
    typeof batteryPctRaw === 'number' ? batteryPctRaw : Number(batteryPctRaw);
  const batteryPct =
    Number.isFinite(batteryPctCandidate) && batteryPctCandidate >= 0
      ? batteryPctCandidate
      : null;

  const recommendations = [
    Number.isFinite(windSpeed) && windSpeed > 8
      ? 'High wind at altitude. Consider rescheduling sensitive flights.'
      : null,
    batteryPct !== null && batteryPct < 35
      ? 'Battery reserve below target. Plan shorter routes.'
      : null,
    Number.isFinite(linkQuality) && linkQuality < 50
      ? 'Link quality degraded. Verify uplink and ground station positioning.'
      : null,
  ].filter(Boolean) as string[];

  return (
    <>
      <Header />
      <PageLayout
        eyebrow="Insights"
        title="Field intelligence and operating signals"
        description="Track flight trends, coverage, recent events, and live recommendations without leaving the dashboard flow."
        metrics={[
          {
            label: 'Survey hours',
            value: formatHours(data?.summary?.flight_hours_7d),
            caption: 'Last 7 days',
          },
          {
            label: 'Flights today',
            value: formatNumber(data?.summary?.flights_24h),
            caption: 'Completed or active',
          },
          {
            label: 'Telemetry link',
            value: isConnected ? 'Live' : 'Offline',
            caption: 'Current session state',
          },
        ]}
      >
        {error ? <Alert severity="warning">{error}</Alert> : null}

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Suspense fallback={<PanelSkeleton height={360} />}>
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
                          id: 'hours',
                          label: 'Hours',
                          data: flightHours,
                        },
                      ]
                    : undefined
                }
              />
            </Suspense>
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Suspense fallback={<PanelSkeleton height={360} />}>
              <ChartUserByCountry
                segments={data?.coverage}
                totalLabel="Coverage segments"
              />
            </Suspense>
          </Grid>
        </Grid>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Suspense fallback={<PanelSkeleton height={330} />}>
              <PageViewsBarChart
                title="Activity mix"
                totalValue={formatNumber(data?.summary?.flights_24h)}
                deltaLabel={activityDelta}
                subtitle="Flights and telemetry points for the last 7 days"
                labels={hasActivityData ? labels.slice(-7) : undefined}
                series={
                  hasActivityData
                    ? [
                        { id: 'flights', label: 'Flights', data: flightCounts.slice(-7) },
                        {
                          id: 'telemetry',
                          label: 'Telemetry',
                          data: telemetryCounts.slice(-7),
                        },
                      ]
                    : undefined
                }
              />
            </Suspense>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <PageSection
              title="Recommendations"
              description="Operational suggestions based on live link, battery, and wind conditions."
              action={
                <Chip
                  size="small"
                  label={isConnected ? 'Live telemetry' : 'Telemetry offline'}
                  color={isConnected ? 'success' : 'default'}
                />
              }
              sx={{ height: '100%' }}
            >
              {loading && !data ? (
                <PanelSkeleton height={250} />
              ) : recommendations.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No critical recommendations. Operations are within optimal bounds.
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
            </PageSection>
          </Grid>
        </Grid>

        <PageSection
          title="Recent events"
          description="Notable system and mission events recorded in the current analytics window."
          action={<Chip size="small" label={`${data?.events?.length ?? 0} events`} />}
        >
          {data?.events && data.events.length > 0 ? (
            <Stack spacing={1.5}>
              {data.events.map((evt) => (
                <Paper key={evt.id} variant="outlined" sx={{ p: 2 }}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                    <Chip size="small" label={evt.type} color="warning" sx={{ width: 'fit-content' }} />
                    <Stack spacing={0.5}>
                      <Typography variant="body2">
                        Flight #{evt.flight_id} • {new Date(evt.created_at).toLocaleString()}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {formatEventData(evt.data)}
                      </Typography>
                    </Stack>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No events recorded in the current window.
            </Typography>
          )}
        </PageSection>

        {/* ---- Telemetry replay chart ---- */}
        <PageSection
          title="Flight telemetry replay"
          description="Aggregated altitude, groundspeed, and battery across a completed flight at 1 s, 10 s, or 1-minute resolution."
          action={
            recentFlights.length > 0 ? (
              <Select
                size="small"
                value={activeFlightId ?? ''}
                onChange={(e) => setSelectedFlightId(Number(e.target.value))}
                sx={{ minWidth: 160, fontSize: 13 }}
              >
                {recentFlights.map((f) => (
                  <MenuItem key={f.id} value={f.id}>
                    Flight #{f.id} — {f.status}
                  </MenuItem>
                ))}
              </Select>
            ) : undefined
          }
        >
          {activeFlightId != null ? (
            <Suspense fallback={<PanelSkeleton height={340} />}>
              <FlightReplayChart
                flightId={activeFlightId}
                title={`Flight #${activeFlightId}`}
              />
            </Suspense>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No completed flights available for replay.
            </Typography>
          )}
        </PageSection>
      </PageLayout>
    </>
  );
}
