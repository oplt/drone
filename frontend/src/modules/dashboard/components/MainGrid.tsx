import { Suspense, lazy, useMemo } from 'react';
import Grid from '@mui/material/Grid';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Copyright from "../../session/components/Copyright";
import HighlightedCard from "./HighlightedCard";
import StatCard, { type StatCardProps } from "./StatCard";
import { useAnalyticsOverview } from "../hooks/useAnalyticsOverview";
import { useTelemetryWebSocket } from "../../mission-runtime";
import { useAlertCenter } from "../../alerts";
import PageLayout, { PageSection } from "../../../shared/layout/PageLayout";

const ChartUserByCountry = lazy(() => import('./ChartUserByCountry'));
const CustomizedTreeView = lazy(() => import('./CustomizedTreeView'));
const CustomizedDataGrid = lazy(() => import('./CustomizedDataGrid'));
const PageViewsBarChart = lazy(() => import('./PageViewsBarChart'));
const SessionsChart = lazy(() => import('./SessionsChart'));

const formatNumber = (value: number | null | undefined, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return `${value.toLocaleString()}${suffix}`;
};

const formatDuration = (minutes: number | null | undefined) => {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return '--';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h}h ${m}m`;
};

const formatTime = (iso?: string | null) => {
  if (!iso) return '--';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return '--';
  return dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

const formatDateLabel = (iso: string) => {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const trendFromSeries = (series: number[]) => {
  if (series.length < 2) return 'neutral' as const;
  const last = series[series.length - 1];
  const prev = series[series.length - 2];
  if (last > prev) return 'up' as const;
  if (last < prev) return 'down' as const;
  return 'neutral' as const;
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

function PanelSkeleton({ height = 280 }: { height?: number }) {
  return (
    <Paper variant="outlined" sx={{ p: 3, borderRadius: 4, minHeight: height }}>
      <Stack spacing={2}>
        <Skeleton variant="rounded" width="36%" height={24} />
        <Skeleton variant="rounded" width="100%" height={height - 60} />
      </Stack>
    </Paper>
  );
}

export default function MainGrid() {
  const { data, loading, error, refresh } = useAnalyticsOverview();
  const { alerts: activeAlerts } = useAlertCenter();
  const system = data?.system;
  const wsEnabled = Boolean(system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });

  const summary = data?.summary;
  const trends = data?.trends;
  const lastUpdateAge =
    system?.last_update && system.last_update > 0
      ? Math.max(0, Math.round(Date.now() / 1000 - system.last_update))
      : null;

  const days = trends?.days ?? [];
  const labels = days.map(formatDateLabel);
  const showInitialSkeleton = loading && !data;

  const statCards = useMemo<StatCardProps[]>(() => {
    const flightCounts = trends?.flight_counts ?? [];
    const telemetryCounts = trends?.telemetry_counts ?? [];
    const flightHours = trends?.flight_hours ?? [];

    return [
      {
        title: 'Active field flights',
        value: formatNumber(summary?.active_flights),
        interval: 'Right now',
        trend: trendFromSeries(flightCounts),
        deltaLabel: deltaLabelFromSeries(flightCounts),
        data: flightCounts,
        labels,
      },
      {
        title: 'Survey hours',
        value: formatNumber(summary?.flight_hours_7d, 'h'),
        interval: 'Last 7 days',
        trend: trendFromSeries(flightHours),
        deltaLabel: deltaLabelFromSeries(flightHours),
        data: flightHours,
        labels,
      },
      {
        title: 'Telemetry frames',
        value: formatNumber(summary?.telemetry_24h),
        interval: 'Last 24 hours',
        trend: trendFromSeries(telemetryCounts),
        deltaLabel: deltaLabelFromSeries(telemetryCounts),
        data: telemetryCounts,
        labels,
      },
      {
        title: 'Avg battery health',
        value:
          summary?.avg_battery_24h !== null && summary?.avg_battery_24h !== undefined
            ? `${summary.avg_battery_24h}%`
            : '--',
        interval: 'Last 24 hours',
        trend:
          summary?.avg_battery_24h !== null &&
          summary?.avg_battery_24h !== undefined &&
          summary.avg_battery_24h < 40
            ? 'down'
            : 'neutral',
        data: [],
      },
    ];
  }, [labels, summary, trends]);

  const recentRows = useMemo(() => {
    if (!data?.recent_flights) return [];
    return data.recent_flights.map((flight) => {
      const normalizedStatus = String(flight.status ?? '').toLowerCase();
      return {
        id: flight.id,
        plan: flight.name,
        status:
          ['active', 'in_progress', 'running'].includes(normalizedStatus)
            ? 'Active'
            : normalizedStatus === 'paused'
              ? 'Paused'
              : ['interrupted', 'aborted'].includes(normalizedStatus)
                ? 'Interrupted'
                : normalizedStatus === 'failed'
                  ? 'Failed'
                  : 'Completed',
        duration: formatDuration(flight.duration_min),
        distance: `${flight.distance_km.toFixed(1)} km`,
        telemetry_points: flight.telemetry_points,
        started_at: formatTime(flight.started_at),
      };
    });
  }, [data?.recent_flights]);

  const telemetryBatteryRaw = telemetry?.battery?.remaining ?? telemetry?.battery_remaining ?? null;
  const telemetryBattery =
    typeof telemetryBatteryRaw === 'number' ? telemetryBatteryRaw : Number(telemetryBatteryRaw);
  const telemetryBatterySafe =
    Number.isFinite(telemetryBattery) && telemetryBattery >= 0 ? telemetryBattery : null;
  const telemetrySpeedRaw = telemetry?.status?.groundspeed ?? telemetry?.groundspeed ?? null;
  const telemetryAltRaw =
    telemetry?.position?.relative_alt ?? telemetry?.position?.relative_altitude ?? null;
  const telemetrySpeed =
    typeof telemetrySpeedRaw === 'number' ? telemetrySpeedRaw : Number(telemetrySpeedRaw);
  const telemetryAlt =
    typeof telemetryAltRaw === 'number' ? telemetryAltRaw : Number(telemetryAltRaw);
  const telemetryMode = telemetry?.mode ?? telemetry?.status?.mode ?? 'UNKNOWN';
  const gpsSatellitesRaw = telemetry?.gps?.satellites ?? telemetry?.gps?.satellite_count ?? null;
  const gpsHdopRaw = telemetry?.gps?.hdop ?? null;
  const gpsSatellites =
    typeof gpsSatellitesRaw === 'number' ? gpsSatellitesRaw : Number(gpsSatellitesRaw);
  const gpsHdop = typeof gpsHdopRaw === 'number' ? gpsHdopRaw : Number(gpsHdopRaw);

  const fallbackAlertItems = [
    system && !system.telemetry_running ? 'Telemetry stream is offline.' : null,
    telemetryBatterySafe !== null && telemetryBatterySafe < 30
      ? `Battery health low (${Math.round(telemetryBatterySafe)}%).`
      : null,
    system && !isConnected ? 'Live telemetry link disconnected.' : null,
  ].filter(Boolean) as string[];
  const alertItems =
    activeAlerts.length > 0
      ? activeAlerts.slice(0, 4).map((item) => `${item.title}: ${item.message}`)
      : fallbackAlertItems;

  const last7Labels = labels.slice(-7);
  const last7Flights = (trends?.flight_counts ?? []).slice(-7);
  const last7Telemetry = (trends?.telemetry_counts ?? []).slice(-7);
  const hasTrendData = (trends?.flight_hours?.length ?? 0) > 0;
  const hasWorkloadData = last7Flights.length > 0 || last7Telemetry.length > 0;
  const surveyDelta = deltaLabelFromSeries(trends?.flight_hours ?? []);
  const workloadDelta = deltaLabelFromSeries(trends?.flight_counts ?? []);

  return (
    <PageLayout
      eyebrow="Operations pulse"
      title="Live command overview"
      description="Monitor field operations, route execution, telemetry health, and coverage trends from one command surface."
      actions={
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
          <Chip
            size="small"
            color={system?.telemetry_running ? 'success' : 'warning'}
            label={system?.telemetry_running ? 'Telemetry live' : 'Telemetry offline'}
          />
          <Chip
            size="small"
            color={system?.mavlink_connected ? 'success' : 'default'}
            label={system?.mavlink_connected ? 'MAVLink connected' : 'MAVLink idle'}
          />
          <Button variant="contained" size="small" onClick={refresh}>
            Refresh data
          </Button>
        </Stack>
      }
      metrics={[
        {
          label: 'Open alerts',
          value: `${activeAlerts.length || alertItems.length}`,
          caption: activeAlerts.length > 0 ? 'Requires review' : 'Systems nominal',
        },
        {
          label: 'Live clients',
          value: `${system?.active_connections ?? 0}`,
          caption: 'Connected operator sessions',
        },
        {
          label: 'Last telemetry',
          value: lastUpdateAge !== null ? `${lastUpdateAge}s` : '--',
          caption: 'Since latest heartbeat',
        },
      ]}
      hero={
        <PageSection
          title="Operational alerts"
          description="Warnings and watch items surfaced from telemetry and route health."
          sx={{ height: '100%', p: 2.5 }}
        >
          {alertItems.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No critical alerts detected. Systems are operating within safe bounds.
            </Typography>
          ) : (
            <Stack spacing={1}>
              {alertItems.map((item) => (
                <Alert key={item} severity="warning">
                  {item}
                </Alert>
              ))}
            </Stack>
          )}
        </PageSection>
      }
    >
      {error ? <Alert severity="warning">{error}</Alert> : null}

      <Typography component="h2" variant="h6">
        Field operations overview
      </Typography>
      <Grid container spacing={2} columns={12}>
        {(showInitialSkeleton ? Array.from({ length: 4 }) : statCards).map((card, index) => (
          <Grid key={showInitialSkeleton ? `stat-skeleton-${index}` : (card as StatCardProps).title} size={{ xs: 12, sm: 6, lg: 3 }}>
            {showInitialSkeleton ? (
              <PanelSkeleton height={190} />
            ) : (
              <StatCard {...(card as StatCardProps)} />
            )}
          </Grid>
        ))}
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          {showInitialSkeleton ? <PanelSkeleton height={190} /> : <HighlightedCard />}
        </Grid>
      </Grid>

      <Grid container spacing={2} columns={12}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <PageSection
            title="Live telemetry"
            description="Streaming vehicle health, mode state, battery reserve, and GPS quality."
            action={
              <Chip
                size="small"
                color={isConnected ? 'success' : 'default'}
                label={isConnected ? 'Live' : 'Offline'}
              />
            }
            sx={{ height: '100%' }}
          >
            {showInitialSkeleton ? (
              <PanelSkeleton height={260} />
            ) : (
              <Stack spacing={3}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Typography variant="caption" color="text.secondary">
                      Flight mode
                    </Typography>
                    <Typography variant="h6">{telemetryMode}</Typography>
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Typography variant="caption" color="text.secondary">
                      Altitude
                    </Typography>
                    <Typography variant="h6">
                      {Number.isFinite(telemetryAlt) ? `${telemetryAlt.toFixed(1)} m` : '--'}
                    </Typography>
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Typography variant="caption" color="text.secondary">
                      Groundspeed
                    </Typography>
                    <Typography variant="h6">
                      {Number.isFinite(telemetrySpeed) ? `${telemetrySpeed.toFixed(1)} m/s` : '--'}
                    </Typography>
                  </Grid>
                  <Grid size={{ xs: 6, md: 3 }}>
                    <Typography variant="caption" color="text.secondary">
                      Battery
                    </Typography>
                    <Typography variant="h6">
                      {telemetryBatterySafe !== null ? `${Math.round(telemetryBatterySafe)}%` : '--'}
                    </Typography>
                  </Grid>
                </Grid>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <Box sx={{ flex: 1 }}>
                    <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.75 }}>
                      <Typography variant="caption" color="text.secondary">
                        GPS strength
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {Number.isFinite(gpsSatellites) ? gpsSatellites : '--'} sats • HDOP{' '}
                        {Number.isFinite(gpsHdop) ? gpsHdop.toFixed(1) : '--'}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={
                        Number.isFinite(gpsSatellites) ? Math.min(100, (gpsSatellites as number) * 8) : 0
                      }
                      sx={{ height: 8, borderRadius: 999 }}
                    />
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.75 }}>
                      <Typography variant="caption" color="text.secondary">
                        Battery reserve
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600 }}>
                        {telemetryBatterySafe !== null ? `${Math.round(telemetryBatterySafe)}%` : '--'}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={telemetryBatterySafe ?? 0}
                      color={telemetryBatterySafe !== null && telemetryBatterySafe < 30 ? 'error' : 'primary'}
                      sx={{ height: 8, borderRadius: 999 }}
                    />
                  </Box>
                </Stack>
              </Stack>
            )}
          </PageSection>
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Suspense fallback={<PanelSkeleton height={390} />}>
            <ChartUserByCountry segments={data?.coverage} totalLabel="Flight coverage" />
          </Suspense>
        </Grid>
      </Grid>

      <Grid container spacing={2} columns={12}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Suspense fallback={<PanelSkeleton height={360} />}>
            <SessionsChart
              title="Survey hours"
              totalValue={formatNumber(summary?.flight_hours_7d, 'h')}
              deltaLabel={surveyDelta}
              subtitle="Survey hours per day for the last 30 days"
              labels={hasTrendData ? labels : undefined}
              series={
                hasTrendData
                  ? [
                      {
                        id: 'hours',
                        label: 'Hours',
                        data: trends?.flight_hours ?? [],
                      },
                    ]
                  : undefined
              }
            />
          </Suspense>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Suspense fallback={<PanelSkeleton height={360} />}>
            <PageViewsBarChart
              title="Workload mix"
              totalValue={formatNumber(summary?.flights_24h)}
              deltaLabel={workloadDelta}
              subtitle="Flights and telemetry points for the last 7 days"
              labels={hasWorkloadData ? last7Labels : undefined}
              series={
                hasWorkloadData
                  ? [
                      { id: 'flights', label: 'Flights', data: last7Flights },
                      { id: 'telemetry', label: 'Telemetry', data: last7Telemetry },
                    ]
                  : undefined
              }
            />
          </Suspense>
        </Grid>
      </Grid>

      <Typography component="h2" variant="h6">
        Equipment health
      </Typography>
      <Grid container spacing={2} columns={12}>
        <Grid size={{ xs: 12, lg: 9 }}>
          <PageSection
            title="Recent flights"
            description="Mission duration, distance, and telemetry volume across the latest runs."
          >
            <Suspense fallback={<PanelSkeleton height={500} />}>
              <CustomizedDataGrid rows={recentRows} loading={loading} />
            </Suspense>
          </PageSection>
        </Grid>
        <Grid size={{ xs: 12, lg: 3 }}>
          <Stack gap={2}>
            <Suspense fallback={<PanelSkeleton height={280} />}>
              <CustomizedTreeView
                summary={summary}
                system={system}
                coverage={data?.coverage}
              />
            </Suspense>
            <PageSection title="System status">
              <Stack spacing={1.25}>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="body2" color="text.secondary">
                    WebSocket
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {system?.telemetry_running ? 'Running' : 'Stopped'}
                  </Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="body2" color="text.secondary">
                    Active clients
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {system?.active_connections ?? 0}
                  </Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="body2" color="text.secondary">
                    MAVLink
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {system?.mavlink_connected ? 'Connected' : 'Idle'}
                  </Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="body2" color="text.secondary">
                    Last telemetry
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {lastUpdateAge !== null ? `${lastUpdateAge}s ago` : '--'}
                  </Typography>
                </Stack>
              </Stack>
            </PageSection>
          </Stack>
        </Grid>
      </Grid>
      <Copyright sx={{ my: 4 }} />
    </PageLayout>
  );
}
