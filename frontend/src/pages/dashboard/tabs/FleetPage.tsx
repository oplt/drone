import { Suspense, lazy, useMemo } from 'react';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Header from '../../../components/dashboard/Header';
import PageLayout, { PageSection } from '../../../components/dashboard/PageLayout';
import useAnalyticsOverview from '../../../hooks/useAnalyticsOverview';
import useTelemetryWebSocket from '../../../hooks/useTelemetryWebsocket';

const CustomizedDataGrid = lazy(() => import('../../../components/dashboard/CustomizedDataGrid'));

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

function PanelSkeleton({ height = 320 }: { height?: number }) {
  return (
    <Paper variant="outlined" sx={{ p: 3, borderRadius: 4, minHeight: height }}>
      <Stack spacing={2}>
        <Skeleton variant="rounded" width="34%" height={24} />
        <Skeleton variant="rounded" width="100%" height={height - 60} />
      </Stack>
    </Paper>
  );
}

export default function FleetPage() {
  const { data, loading } = useAnalyticsOverview();
  const wsEnabled = Boolean(data?.system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });
  const system = data?.system;

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

  const linkQualityRaw = telemetry?.link?.telemetry ?? telemetry?.link?.rc ?? null;
  const windSpeedRaw = telemetry?.wind?.speed ?? null;
  const batteryPctRaw = telemetry?.battery?.remaining ?? null;
  const linkQuality =
    typeof linkQualityRaw === 'number' ? linkQualityRaw : Number(linkQualityRaw);
  const windSpeed = typeof windSpeedRaw === 'number' ? windSpeedRaw : Number(windSpeedRaw);
  const batteryPctCandidate =
    typeof batteryPctRaw === 'number' ? batteryPctRaw : Number(batteryPctRaw);
  const batteryPct =
    Number.isFinite(batteryPctCandidate) && batteryPctCandidate >= 0
      ? batteryPctCandidate
      : null;

  return (
    <>
      <Header />
      <PageLayout
        eyebrow="Fleet"
        title="Fleet connectivity and mission readiness"
        description="Watch link quality, battery reserve, and recent missions from one control surface."
        metrics={[
          {
            label: 'Telemetry stream',
            value: system?.telemetry_running ? 'Running' : 'Stopped',
            caption: 'Live backend state',
          },
          {
            label: 'MAVLink',
            value: system?.mavlink_connected ? 'Connected' : 'Idle',
            caption: 'Vehicle link state',
          },
          {
            label: 'Active clients',
            value: `${system?.active_connections ?? 0}`,
            caption: 'Current operator sessions',
          },
        ]}
      >
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 4 }}>
            <PageSection
              title="System link"
              description="Live link quality, wind exposure, and available battery reserve."
              action={
                <Chip
                  size="small"
                  label={isConnected ? 'Live' : 'Offline'}
                  color={isConnected ? 'success' : 'default'}
                />
              }
              sx={{ height: '100%' }}
            >
              <Stack spacing={2}>
                <Box>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="caption" color="text.secondary">
                      Link quality
                    </Typography>
                    <Typography variant="caption" sx={{ fontWeight: 600 }}>
                      {Number.isFinite(linkQuality) ? `${Math.round(linkQuality)}%` : '--'}
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={Number.isFinite(linkQuality) ? linkQuality : 0}
                    sx={{ height: 8, borderRadius: 999 }}
                  />
                </Box>
                <Box>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="caption" color="text.secondary">
                      Wind @ altitude
                    </Typography>
                    <Typography variant="caption" sx={{ fontWeight: 600 }}>
                      {Number.isFinite(windSpeed) ? `${windSpeed.toFixed(1)} m/s` : '--'}
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={Number.isFinite(windSpeed) ? Math.min(100, windSpeed * 8) : 0}
                    sx={{ height: 8, borderRadius: 999 }}
                  />
                </Box>
                <Box>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="caption" color="text.secondary">
                      Battery reserve
                    </Typography>
                    <Typography variant="caption" sx={{ fontWeight: 600 }}>
                      {batteryPct !== null ? `${Math.round(batteryPct)}%` : '--'}
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={batteryPct ?? 0}
                    color={batteryPct !== null && batteryPct < 30 ? 'error' : 'primary'}
                    sx={{ height: 8, borderRadius: 999 }}
                  />
                </Box>
              </Stack>
            </PageSection>
          </Grid>
          <Grid size={{ xs: 12, lg: 8 }}>
            <PageSection
              title="Recent flights"
              description="Flight duration, distance, and telemetry density from the latest missions."
              action={<Chip size="small" label={`${data?.recent_flights?.length ?? 0} flights`} />}
            >
              <Suspense fallback={<PanelSkeleton height={520} />}>
                <CustomizedDataGrid rows={recentRows} loading={loading} />
              </Suspense>
            </PageSection>
          </Grid>
        </Grid>
      </PageLayout>
    </>
  );
}
