import { Suspense, lazy, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Select from '@mui/material/Select';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import BadgeRoundedIcon from '@mui/icons-material/BadgeRounded';
import FlightTakeoffRoundedIcon from '@mui/icons-material/FlightTakeoffRounded';
import Header from "../../../shared/layout/WorkflowHeader";
import PageLayout, { PageSection } from "../../../shared/layout/PageLayout";
import useAnalyticsOverview from "../../../modules/dashboard";
import useTelemetryWebSocket from "../../../modules/mission-runtime";
import {
  createCertification,
  createDevice,
  fetchCertifications,
  fetchDevices,
} from '../api/fleetApi';
import type { CertItem, DeviceItem } from '../types';

const CustomizedDataGrid = lazy(
  () => import("../../dashboard/components/CustomizedDataGrid"),
);

// ---------------------------------------------------------------------------
// Helpers shared with Overview tab
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Certifications tab
// ---------------------------------------------------------------------------

const CERT_TYPES = ['FAA_PART_107', 'ICAO_RPAS', 'OTHER'];

function AddCertDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [certType, setCertType] = useState('FAA_PART_107');
  const [certNumber, setCertNumber] = useState('');
  const [issuedAt, setIssuedAt] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleClose = () => {
    setCertType('FAA_PART_107');
    setCertNumber('');
    setIssuedAt('');
    setExpiresAt('');
    setError('');
    onClose();
  };

  const handleSubmit = async () => {
    if (!certNumber.trim() || !issuedAt) return;
    setSaving(true);
    setError('');
    try {
      await createCertification({
        cert_type: certType,
        cert_number: certNumber.trim(),
        issued_at: issuedAt,
        expires_at: expiresAt || null,
      });
      onCreated();
      handleClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Certification</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Select
            value={certType}
            onChange={(e) => setCertType(e.target.value)}
            fullWidth
            displayEmpty
          >
            {CERT_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t.replace(/_/g, ' ')}
              </MenuItem>
            ))}
          </Select>
          <TextField
            label="Certificate number"
            value={certNumber}
            onChange={(e) => setCertNumber(e.target.value)}
            fullWidth
            autoFocus
          />
          <TextField
            label="Issued at"
            type="date"
            value={issuedAt}
            onChange={(e) => setIssuedAt(e.target.value)}
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="Expires at (optional)"
            type="date"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
          />
          {error && (
            <Typography color="error" variant="body2">
              {error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={saving || !certNumber.trim() || !issuedAt}
        >
          {saving ? 'Adding…' : 'Add'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function CertRow({ cert }: { cert: CertItem }) {
  const expiry = cert.expires_at ? new Date(cert.expires_at).toLocaleDateString() : 'No expiry';
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderRadius: 3, display: 'flex', alignItems: 'center', gap: 2 }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Chip label={cert.cert_type.replace(/_/g, ' ')} size="small" variant="outlined" />
          <Typography variant="body1" fontWeight={600} noWrap>
            {cert.cert_number}
          </Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Issued {new Date(cert.issued_at).toLocaleDateString()} · Expires {expiry}
          {cert.issuing_authority ? ` · ${cert.issuing_authority}` : ''}
        </Typography>
      </Box>
      {cert.document_url && (
        <Tooltip title="View document">
          <IconButton
            size="small"
            component="a"
            href={cert.document_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <BadgeRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Paper>
  );
}

function CertificationsTab() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: certs = [], isLoading } = useQuery({
    queryKey: ['fleet-certifications'],
    queryFn: () => fetchCertifications(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['fleet-certifications'] });

  return (
    <PageSection
      title="Certifications"
      description="Regulatory and authority certifications tied to this fleet."
      action={
        <Button
          variant="contained"
          startIcon={<AddRoundedIcon />}
          onClick={() => setAddOpen(true)}
          size="small"
        >
          Add Certification
        </Button>
      }
    >
      {isLoading && <Typography color="text.secondary">Loading certifications…</Typography>}
      {!isLoading && certs.length === 0 && (
        <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, textAlign: 'center' }}>
          <Typography color="text.secondary">
            No certifications on record. Add one to track regulatory compliance.
          </Typography>
        </Paper>
      )}
      <Stack spacing={1.5}>
        {certs.map((cert) => (
          <CertRow key={cert.id} cert={cert} />
        ))}
      </Stack>

      <AddCertDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={refresh}
      />
    </PageSection>
  );
}

// ---------------------------------------------------------------------------
// Device Readiness tab
// ---------------------------------------------------------------------------

const DEVICE_STATUSES = ['airworthy', 'grounded', 'limited'];

function AddDeviceDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [deviceId, setDeviceId] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [status, setStatus] = useState('airworthy');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleClose = () => {
    setDeviceId('');
    setDeviceName('');
    setStatus('airworthy');
    setNotes('');
    setError('');
    onClose();
  };

  const handleSubmit = async () => {
    if (!deviceId.trim() || !deviceName.trim()) return;
    setSaving(true);
    setError('');
    try {
      await createDevice({
        device_id: deviceId.trim(),
        device_name: deviceName.trim(),
        status,
        notes: notes.trim() || null,
      });
      onCreated();
      handleClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Device</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Device ID"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            fullWidth
            autoFocus
          />
          <TextField
            label="Device name"
            value={deviceName}
            onChange={(e) => setDeviceName(e.target.value)}
            fullWidth
          />
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            fullWidth
            displayEmpty
          >
            {DEVICE_STATUSES.map((s) => (
              <MenuItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </MenuItem>
            ))}
          </Select>
          <TextField
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
          {error && (
            <Typography color="error" variant="body2">
              {error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={saving || !deviceId.trim() || !deviceName.trim()}
        >
          {saving ? 'Adding…' : 'Add'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function deviceStatusColor(
  status: string,
): 'success' | 'error' | 'warning' | 'default' {
  if (status === 'airworthy') return 'success';
  if (status === 'grounded') return 'error';
  if (status === 'limited') return 'warning';
  return 'default';
}

function DeviceRow({ device }: { device: DeviceItem }) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderRadius: 3, display: 'flex', alignItems: 'center', gap: 2 }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="body1" fontWeight={600} noWrap>
            {device.device_name}
          </Typography>
          <Chip
            label={device.status}
            size="small"
            color={deviceStatusColor(device.status)}
          />
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block">
          {device.device_id}
        </Typography>
        {(device.last_inspection_at || device.next_inspection_due) && (
          <Typography variant="caption" color="text.secondary">
            {device.last_inspection_at
              ? `Last inspected ${new Date(device.last_inspection_at).toLocaleDateString()}`
              : ''}
            {device.last_inspection_at && device.next_inspection_due ? ' · ' : ''}
            {device.next_inspection_due
              ? `Next due ${new Date(device.next_inspection_due).toLocaleDateString()}`
              : ''}
          </Typography>
        )}
        {device.notes && (
          <Typography variant="caption" color="text.secondary" display="block">
            {device.notes}
          </Typography>
        )}
      </Box>
      <FlightTakeoffRoundedIcon fontSize="small" color="action" />
    </Paper>
  );
}

function DeviceReadinessTab() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: devices = [], isLoading } = useQuery({
    queryKey: ['fleet-devices'],
    queryFn: () => fetchDevices(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['fleet-devices'] });

  return (
    <PageSection
      title="Device Readiness"
      description="Airworthiness status and inspection schedule for each device in the fleet."
      action={
        <Button
          variant="contained"
          startIcon={<AddRoundedIcon />}
          onClick={() => setAddOpen(true)}
          size="small"
        >
          Add Device
        </Button>
      }
    >
      {isLoading && <Typography color="text.secondary">Loading devices…</Typography>}
      {!isLoading && devices.length === 0 && (
        <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, textAlign: 'center' }}>
          <Typography color="text.secondary">
            No devices on record. Add one to track airworthiness and inspection status.
          </Typography>
        </Paper>
      )}
      <Stack spacing={1.5}>
        {devices.map((device) => (
          <DeviceRow key={device.id} device={device} />
        ))}
      </Stack>

      <AddDeviceDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={refresh}
      />
    </PageSection>
  );
}

// ---------------------------------------------------------------------------
// FleetPage — main export
// ---------------------------------------------------------------------------

export default function FleetPage() {
  const { data, loading } = useAnalyticsOverview();
  const wsEnabled = Boolean(data?.system?.mavlink_connected);
  const { telemetry, isConnected } = useTelemetryWebSocket({ enabled: wsEnabled });
  const system = data?.system;
  const [tab, setTab] = useState(0);

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
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)}>
            <Tab label="Overview" />
            <Tab label="Certifications" />
            <Tab label="Device Readiness" />
          </Tabs>
        </Box>

        {tab === 0 && (
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
        )}

        {tab === 1 && <CertificationsTab />}
        {tab === 2 && <DeviceReadinessTab />}
      </PageLayout>
    </>
  );
}
