import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DownloadIcon from "@mui/icons-material/Download";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import WarningIcon from "@mui/icons-material/Warning";
import FlightIcon from "@mui/icons-material/Flight";
import PauseCircleIcon from "@mui/icons-material/PauseCircle";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import PersonIcon from "@mui/icons-material/Person";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import { useTheme } from "@mui/material/styles";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function formatTs(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  const color =
    upper === "PASS" || upper === "completed"
      ? "success"
      : upper === "WARN"
        ? "warning"
        : "error";
  return <Chip label={upper} color={color as any} size="small" sx={{ fontWeight: 600 }} />;
}

function PreflightSection({ data }: { data: any }) {
  const [open, setOpen] = useState(false);
  const theme = useTheme();

  const statusColor =
    data.overall_status === "PASS"
      ? theme.palette.success.main
      : data.overall_status === "WARN"
        ? theme.palette.warning.main
        : theme.palette.error.main;

  const allChecks = [...(data.base_checks ?? []), ...(data.mission_checks ?? [])];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} justifyContent="space-between">
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box
            sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: statusColor, flexShrink: 0 }}
          />
          <Typography fontWeight={600}>Preflight</Typography>
          <StatusBadge status={data.overall_status} />
          {data.summary && (
            <Typography variant="caption" color="text.secondary">
              {data.summary.passed ?? 0} pass · {data.summary.warned ?? 0} warn ·{" "}
              {data.summary.failed ?? 0} fail
            </Typography>
          )}
        </Stack>
        <IconButton size="small" onClick={() => setOpen((v) => !v)}>
          {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
        </IconButton>
      </Stack>
      {data.started_at && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
          {formatTs(data.started_at)} → {formatTs(data.completed_at)}
        </Typography>
      )}
      <Collapse in={open}>
        <Stack spacing={0.5} sx={{ mt: 1.5 }}>
          {allChecks.map((check: any, i: number) => (
            <Stack key={i} direction="row" alignItems="center" spacing={1}>
              {check.status === "PASS" ? (
                <CheckCircleIcon fontSize="small" color="success" />
              ) : check.status === "WARN" ? (
                <WarningIcon fontSize="small" color="warning" />
              ) : (
                <ErrorIcon fontSize="small" color="error" />
              )}
              <Typography variant="body2" sx={{ flex: 1 }}>
                {check.name}
              </Typography>
              {check.message && (
                <Typography variant="caption" color="text.secondary">
                  {check.message}
                </Typography>
              )}
            </Stack>
          ))}
          {allChecks.length === 0 && (
            <Typography variant="caption" color="text.secondary">
              No checks recorded.
            </Typography>
          )}
        </Stack>
      </Collapse>
    </Paper>
  );
}

function stateIcon(state: string) {
  switch (state) {
    case "running":
    case "airborne":
      return <FlightIcon fontSize="small" color="primary" />;
    case "paused":
      return <PauseCircleIcon fontSize="small" color="warning" />;
    case "completed":
      return <CheckCircleIcon fontSize="small" color="success" />;
    case "aborted":
    case "failed":
      return <StopCircleIcon fontSize="small" color="error" />;
    default:
      return <FlightIcon fontSize="small" color="disabled" />;
  }
}

function TransitionItem({ item }: { item: any }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ pt: 0.25 }}>{stateIcon(item.state)}</Box>
      <Box>
        <Typography variant="body2" fontWeight={500}>
          {item.state}
          {item.trigger && (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
              via {item.trigger}
            </Typography>
          )}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {formatTs(item.entered_at)}
        </Typography>
        {item.reason && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {item.reason}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}

function CommandItem({ item }: { item: any }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ pt: 0.25 }}>
        <PersonIcon fontSize="small" color={item.accepted ? "primary" : "disabled"} />
      </Box>
      <Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" fontWeight={500}>
            {item.command}
          </Typography>
          <Chip
            label={item.accepted ? "accepted" : "rejected"}
            size="small"
            color={item.accepted ? "success" : "default"}
          />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {formatTs(item.requested_at)} · {item.state_before} → {item.state_after}
        </Typography>
        {item.message && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {item.message}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}

function EventItem({ item }: { item: any }) {
  const [open, setOpen] = useState(false);
  const hasData = item.data && Object.keys(item.data).length > 0;

  return (
    <Stack direction="row" spacing={1.5} alignItems="flex-start">
      <Box sx={{ pt: 0.25 }}>
        <NotificationsActiveIcon fontSize="small" color="action" />
      </Box>
      <Box sx={{ flex: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" fontWeight={500}>
            {item.type}
          </Typography>
          {hasData && (
            <IconButton size="small" onClick={() => setOpen((v) => !v)} sx={{ p: 0 }}>
              {open ? (
                <KeyboardArrowUpIcon fontSize="small" />
              ) : (
                <KeyboardArrowDownIcon fontSize="small" />
              )}
            </IconButton>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {formatTs(item.created_at)}
        </Typography>
        <Collapse in={open}>
          <Box
            component="pre"
            sx={{
              mt: 0.5,
              p: 1,
              bgcolor: "action.hover",
              borderRadius: 1,
              fontSize: 11,
              overflow: "auto",
              maxHeight: 200,
            }}
          >
            {JSON.stringify(item.data, null, 2)}
          </Box>
        </Collapse>
      </Box>
    </Stack>
  );
}

type TimelineEntry =
  | { kind: "transition"; ts: number; data: any }
  | { kind: "command"; ts: number; data: any }
  | { kind: "event"; ts: number; data: any };

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function ExportButton({ flightId }: { flightId: string }) {
  const [jobId, setJobId] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);

  const { data: jobStatus } = useQuery({
    queryKey: ["export-job", flightId, jobId],
    queryFn: () => fetchJSON<any>(`/tasks/missions/${flightId}/export/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : 3000;
    },
  });

  const handleExport = async () => {
    if (starting) return;
    setStarting(true);
    try {
      const res = await postJSON<{ job_id: number }>(`/tasks/missions/${flightId}/export`);
      setJobId(res.job_id);
    } catch {
      // ignore
    } finally {
      setStarting(false);
    }
  };

  if (jobStatus?.status === "ready" && jobStatus.download_url) {
    return (
      <Button
        size="small"
        variant="outlined"
        startIcon={<DownloadIcon />}
        onClick={() => window.open(jobStatus.download_url, "_blank")}
      >
        Download ZIP
      </Button>
    );
  }

  if (jobId && jobStatus?.status === "failed") {
    return (
      <Button size="small" color="error" onClick={() => setJobId(null)}>
        Export failed — retry
      </Button>
    );
  }

  if (jobId && jobStatus && jobStatus.status !== "ready") {
    return (
      <Stack direction="row" alignItems="center" spacing={1}>
        <CircularProgress size={16} />
        <Typography variant="caption" color="text.secondary">
          Preparing export…
        </Typography>
      </Stack>
    );
  }

  return (
    <Button
      size="small"
      variant="outlined"
      startIcon={starting ? <CircularProgress size={14} /> : <DownloadIcon />}
      onClick={handleExport}
      disabled={starting}
    >
      Export
    </Button>
  );
}

function ComplianceSection({ data }: { data: any }) {
  const [open, setOpen] = useState(false);
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} justifyContent="space-between">
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography fontWeight={600}>Compliance</Typography>
          <Chip
            label={data.remote_id_status ?? "unknown"}
            size="small"
            color={data.remote_id_status === "broadcast" ? "success" : "default"}
          />
          {data.laanc_auth_number && (
            <Chip label={`LAANC: ${data.laanc_auth_number}`} size="small" variant="outlined" />
          )}
        </Stack>
        <IconButton size="small" onClick={() => setOpen((v) => !v)}>
          {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
        </IconButton>
      </Stack>
      <Collapse in={open}>
        <Stack spacing={1} sx={{ mt: 1.5 }}>
          {data.preflight_ack_at && (
            <Box>
              <Typography variant="caption" color="text.secondary">Preflight acknowledged</Typography>
              <Typography variant="body2">{new Date(data.preflight_ack_at).toLocaleString()}</Typography>
            </Box>
          )}
          {data.laanc_auth_expires && (
            <Box>
              <Typography variant="caption" color="text.secondary">LAANC expires</Typography>
              <Typography variant="body2">{new Date(data.laanc_auth_expires).toLocaleString()}</Typography>
            </Box>
          )}
          {data.notes && (
            <Box>
              <Typography variant="caption" color="text.secondary">Notes</Typography>
              <Typography variant="body2">{data.notes}</Typography>
            </Box>
          )}
        </Stack>
      </Collapse>
    </Paper>
  );
}

export default function MissionTimeline() {
  const { flightId } = useParams<{ flightId: string }>();
  const navigate = useNavigate();

  const [missionQ, preflightQ, transitionsQ, commandsQ, eventsQ, complianceQ] = useQueries({
    queries: [
      {
        queryKey: ["mission", flightId],
        queryFn: () => fetchJSON<any>(`/tasks/missions/${flightId}`),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-preflight", flightId],
        queryFn: () => fetchJSON<any>(`/tasks/missions/${flightId}/preflight`),
        enabled: Boolean(flightId),
        retry: false,
      },
      {
        queryKey: ["mission-transitions", flightId],
        queryFn: () => fetchJSON<any[]>(`/tasks/missions/${flightId}/transitions`),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-commands", flightId],
        queryFn: () => fetchJSON<any[]>(`/tasks/missions/${flightId}/commands`),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-events", flightId],
        queryFn: () => fetchJSON<any[]>(`/tasks/missions/${flightId}/events`),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-compliance", flightId],
        queryFn: () => fetchJSON<any>(`/tasks/missions/${flightId}/compliance`),
        enabled: Boolean(flightId),
        retry: false,
      },
    ],
  });

  const loading =
    missionQ.isLoading ||
    transitionsQ.isLoading ||
    commandsQ.isLoading ||
    eventsQ.isLoading;

  // Build merged, sorted timeline
  const entries: TimelineEntry[] = [];

  (transitionsQ.data ?? []).forEach((item: any) => {
    entries.push({ kind: "transition", ts: item.entered_at ?? 0, data: item });
  });
  (commandsQ.data ?? []).forEach((item: any) => {
    entries.push({ kind: "command", ts: item.requested_at ?? 0, data: item });
  });
  (eventsQ.data ?? []).forEach((item: any) => {
    entries.push({ kind: "event", ts: item.created_at ?? 0, data: item });
  });

  entries.sort((a, b) => a.ts - b.ts);

  const mission = missionQ.data;

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1100, mx: "auto" }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <Tooltip title="Back">
          <IconButton onClick={() => navigate(-1)} size="small">
            <ArrowBackIcon />
          </IconButton>
        </Tooltip>
        <Typography variant="h6" fontWeight={700}>
          Mission Timeline
        </Typography>
        {mission && (
          <Chip label={mission.state} size="small" />
        )}
        <Box sx={{ flex: 1 }} />
        {flightId && <ExportButton flightId={flightId} />}
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "280px 1fr" },
          gap: 2,
          alignItems: "start",
        }}
      >
        {/* Sidebar — mission summary */}
        <Paper variant="outlined" sx={{ p: 2 }}>
          {missionQ.isLoading ? (
            <CircularProgress size={24} />
          ) : missionQ.error ? (
            <Typography color="error" variant="body2">
              Failed to load mission.
            </Typography>
          ) : mission ? (
            <Stack spacing={1}>
              <Typography fontWeight={700} noWrap>
                {mission.mission_name}
              </Typography>
              <Divider />
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Type
                </Typography>
                <Typography variant="body2">{mission.mission_type}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  State
                </Typography>
                <Typography variant="body2">{mission.state}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Created
                </Typography>
                <Typography variant="body2">{formatTs(mission.created_at)}</Typography>
              </Box>
              {mission.updated_at && (
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Last updated
                  </Typography>
                  <Typography variant="body2">{formatTs(mission.updated_at)}</Typography>
                </Box>
              )}
              {mission.preflight_run_id && (
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Preflight ID
                  </Typography>
                  <Typography variant="body2" sx={{ wordBreak: "break-all", fontSize: 11 }}>
                    {mission.preflight_run_id}
                  </Typography>
                </Box>
              )}
              {mission.last_error && (
                <Box>
                  <Typography variant="caption" color="error">
                    Error
                  </Typography>
                  <Typography variant="body2" color="error">
                    {mission.last_error}
                  </Typography>
                </Box>
              )}
            </Stack>
          ) : null}
        </Paper>

        {/* Main — timeline */}
        <Stack spacing={2}>
          {/* Preflight */}
          {preflightQ.data && <PreflightSection data={preflightQ.data} />}

          {/* Compliance */}
          {complianceQ.data && <ComplianceSection data={complianceQ.data} />}

          {/* Chronological timeline */}
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress />
            </Box>
          ) : entries.length === 0 ? (
            <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
              <Typography color="text.secondary">No timeline events recorded.</Typography>
            </Paper>
          ) : (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1.5 }}>
                Events ({entries.length})
              </Typography>
              <Stack
                spacing={0}
                divider={<Divider sx={{ my: 1 }} />}
              >
                {entries.map((entry, i) => {
                  if (entry.kind === "transition") {
                    return <TransitionItem key={`t-${i}`} item={entry.data} />;
                  }
                  if (entry.kind === "command") {
                    return <CommandItem key={`c-${i}`} item={entry.data} />;
                  }
                  return <EventItem key={`e-${i}`} item={entry.data} />;
                })}
              </Stack>
            </Paper>
          )}
        </Stack>
      </Box>
    </Box>
  );
}
