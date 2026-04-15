import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import TimelineIcon from "@mui/icons-material/Timeline";
import { getToken } from "../../../auth";
import { useMissionCommandMetrics } from "../../../hooks/useMissionCommandMetrics";
import {
  getMissionStateTransitions,
  getOpsHealth,
  getMissionCommandAudit,
  type MissionStateTransitionResponse,
  type OpsHealthResponse,
  sendMissionCommand,
  type MissionCommand,
  type MissionCommandAuditResponse,
  type MissionLifecycleState,
} from "../../../utils/api";

type MissionStatusLike = {
  flight_id?: string;
  mission_name?: string;
  mission_lifecycle?: {
    flight_id?: string | null;
    state?: MissionLifecycleState;
    mission_name?: string;
    mission_type?: string;
    updated_at?: number;
    last_error?: string | null;
  } | null;
  command_capabilities?: {
    pause?: boolean;
    resume?: boolean;
    abort?: boolean;
  } | null;
};

function StatRow({
  label,
  value,
  valueSx,
}: {
  label: string;
  value: string;
  valueSx?: Record<string, unknown>;
}) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600, ...valueSx }}>
        {value}
      </Typography>
    </Stack>
  );
}

const stateChipColor = (
  state: MissionLifecycleState | null,
): "default" | "info" | "success" | "warning" | "error" => {
  if (state === "queued") return "info";
  if (state === "running") return "success";
  if (state === "paused") return "warning";
  if (state === "completed") return "success";
  if (state === "failed" || state === "aborted") return "error";
  return "default";
};

const formatTs = (unixSeconds?: number): string => {
  if (!unixSeconds || !Number.isFinite(unixSeconds)) return "--";
  return new Date(unixSeconds * 1000).toLocaleString();
};

const toMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "Command request failed";

const opsChipColor = (
  status: OpsHealthResponse["status"] | undefined,
): "default" | "success" | "warning" | "error" => {
  if (status === "healthy") return "success";
  if (status === "degraded") return "warning";
  if (status === "offline") return "error";
  return "default";
};

type TimelineEntry = {
  key: string;
  occurredAt: number;
  kind: "transition" | "command_rejected";
  label: string;
  detail: string;
  state?: string;
};

export function MissionCommandPanel({
  telemetry,
  droneConnected,
  missionStatus = null,
  activeFlightId = null,
  apiBase,
  getTokenFn = getToken,
  title = "Command Panel",
  defaultExpanded = true,
  sx,
}: {
  telemetry: unknown;
  droneConnected: boolean;
  missionStatus?: MissionStatusLike | null;
  activeFlightId?: string | null;
  apiBase?: string;
  getTokenFn?: () => string | null;
  title?: string;
  defaultExpanded?: boolean;
  sx?: SxProps<Theme>;
}) {
  const navigate = useNavigate();
  const {
    flightStatus,
    gpsStrength,
    batteryHealth,
    failsafeState,
    altitudeDisplay,
    batteryCellDisplay,
    linkQuality,
    windDisplay,
    failsafeActive,
  } = useMissionCommandMetrics(telemetry);

  const lifecycle =
    missionStatus?.mission_lifecycle ??
    (missionStatus?.flight_id || missionStatus?.mission_name
      ? {
          flight_id: missionStatus?.flight_id ?? null,
          mission_name: missionStatus?.mission_name,
        }
      : null);
  const lifecycleState = lifecycle?.state ?? null;
  const flightId = lifecycle?.flight_id ?? activeFlightId ?? null;

  const commandCapabilities = useMemo(() => {
    const caps = missionStatus?.command_capabilities;
    if (caps) {
      return {
        pause: Boolean(caps.pause),
        resume: Boolean(caps.resume),
        abort: Boolean(caps.abort),
      };
    }
    return {
      pause: lifecycleState === "running",
      resume: lifecycleState === "paused",
      abort:
        lifecycleState === "queued" ||
        lifecycleState === "running" ||
        lifecycleState === "paused",
    };
  }, [missionStatus?.command_capabilities, lifecycleState]);

  const [audit, setAudit] = useState<MissionCommandAuditResponse[]>([]);
  const [transitions, setTransitions] = useState<MissionStateTransitionResponse[]>([]);
  const [opsHealth, setOpsHealth] = useState<OpsHealthResponse | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);
  const [commandBusy, setCommandBusy] = useState<MissionCommand | null>(null);
  const [commandMessage, setCommandMessage] = useState<string | null>(null);
  const [commandError, setCommandError] = useState<string | null>(null);

  const loadAudit = useCallback(async () => {
    if (!flightId || !apiBase) {
      setAudit([]);
      setAuditError(null);
      return;
    }
    const token = getTokenFn();
    if (!token) {
      setAuditError("Not authenticated");
      setAudit([]);
      return;
    }

    setAuditLoading(true);
    setAuditError(null);
    try {
      const records = await getMissionCommandAudit(flightId, token, apiBase);
      setAudit(records);
    } catch (error) {
      setAuditError(toMessage(error));
    } finally {
      setAuditLoading(false);
    }
  }, [apiBase, flightId, getTokenFn]);

  const loadTransitions = useCallback(async () => {
    if (!flightId || !apiBase) {
      setTransitions([]);
      setTimelineError(null);
      return;
    }
    const token = getTokenFn();
    if (!token) {
      setTimelineError("Not authenticated");
      setTransitions([]);
      return;
    }

    setTimelineError(null);
    try {
      const records = await getMissionStateTransitions(flightId, token, apiBase);
      setTransitions(records);
    } catch (error) {
      setTimelineError(toMessage(error));
    }
  }, [apiBase, flightId, getTokenFn]);

  const loadOpsHealth = useCallback(async () => {
    if (!apiBase) {
      setOpsHealth(null);
      setOpsError(null);
      return;
    }
    const token = getTokenFn();
    if (!token) {
      setOpsHealth(null);
      setOpsError("Not authenticated");
      return;
    }

    setOpsError(null);
    try {
      const snapshot = await getOpsHealth(token, apiBase);
      setOpsHealth(snapshot);
    } catch (error) {
      setOpsError(toMessage(error));
    }
  }, [apiBase, getTokenFn]);

  useEffect(() => {
    void loadAudit();
  }, [loadAudit]);

  useEffect(() => {
    void loadTransitions();
  }, [loadTransitions]);

  useEffect(() => {
    void loadOpsHealth();
  }, [loadOpsHealth]);

  useEffect(() => {
    if (!apiBase) return;
    const handle = window.setInterval(() => {
      void loadOpsHealth();
      if (flightId) {
        void loadAudit();
        void loadTransitions();
      }
    }, 12000);
    return () => window.clearInterval(handle);
  }, [apiBase, flightId, loadAudit, loadOpsHealth, loadTransitions]);

  const recentAudit = useMemo(
    () => [...audit].sort((a, b) => b.requested_at - a.requested_at).slice(0, 8),
    [audit],
  );

  const recentTimeline = useMemo<TimelineEntry[]>(() => {
    const transitionEntries: TimelineEntry[] = transitions.map((entry, index) => ({
      key: `${entry.entered_at}_${entry.trigger}_${index}`,
      occurredAt: entry.entered_at,
      kind: "transition",
      label: entry.state.toUpperCase(),
      detail:
        entry.trigger === "mission_created"
          ? "Mission record created"
          : entry.trigger === "execution_started"
            ? "Execution started"
            : entry.trigger === "execution_ended"
              ? "Mission execution finished"
              : `Triggered by ${entry.trigger.replace("command:", "")}`,
      state: entry.state,
    }));

    const rejectedCommandEntries: TimelineEntry[] = audit
      .filter((entry) => !entry.accepted)
      .map((entry) => ({
        key: `reject_${entry.command_id}`,
        occurredAt: entry.requested_at,
        kind: "command_rejected",
        label: `${entry.command.toUpperCase()} REJECTED`,
        detail: entry.message || `${entry.command} was ignored`,
        state: entry.state_before,
      }));

    return [...transitionEntries, ...rejectedCommandEntries]
      .sort((a, b) => b.occurredAt - a.occurredAt)
      .slice(0, 10);
  }, [audit, transitions]);

  const queueRows = useMemo(() => {
    if (!opsHealth) return [];
    return [
      ["Flight events", opsHealth.queues.db_event],
      ["Lifecycle", opsHealth.queues.db_lifecycle],
      ["Raw ingest", opsHealth.queues.raw_event],
    ] as const;
  }, [opsHealth]);

  const buildIdempotencyKey = useCallback(
    (command: MissionCommand): string => {
      const randomPart =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
      return `${flightId ?? "mission"}_${command}_${randomPart}`.slice(0, 120);
    },
    [flightId],
  );

  const issueCommand = useCallback(
    async (command: MissionCommand) => {
      if (!flightId) {
        setCommandError("No active mission selected.");
        return;
      }
      if (!apiBase) {
        setCommandError("API base URL is not configured.");
        return;
      }
      const token = getTokenFn();
      if (!token) {
        setCommandError("Not authenticated.");
        return;
      }

      setCommandBusy(command);
      setCommandError(null);
      setCommandMessage(null);
      try {
        const idempotencyKey = buildIdempotencyKey(command);
        const result = await sendMissionCommand(
          flightId,
          command,
          token,
          idempotencyKey,
          undefined,
          apiBase,
        );
        setCommandMessage(result.message || `Command '${command}' accepted.`);
        await loadAudit();
        await loadTransitions();
        await loadOpsHealth();
      } catch (error) {
        setCommandError(toMessage(error));
      } finally {
        setCommandBusy(null);
      }
    },
    [apiBase, buildIdempotencyKey, flightId, getTokenFn, loadAudit, loadOpsHealth, loadTransitions],
  );

  return (
    <Accordion
      disableGutters
      defaultExpanded={defaultExpanded}
      sx={[
        {
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
          "&:before": { display: "none" },
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreRoundedIcon />}
        sx={{ px: 2, py: 0.25, minHeight: 0 }}
      >
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
          <Typography variant="subtitle1">{title}</Typography>
          {lifecycleState && (
            <Chip
              size="small"
              label={lifecycleState.toUpperCase()}
              color={stateChipColor(lifecycleState)}
            />
          )}
        </Stack>
      </AccordionSummary>

      <AccordionDetails sx={{ px: 1, pb: 1, pt: 0.5 }}>
        <Stack spacing={0.2}>
          <StatRow
            label="Drone Status"
            value={droneConnected ? "Connected" : "Disconnected"}
          />
          <StatRow
            label="Flight Status"
            value={flightStatus}
            valueSx={{ color: failsafeActive ? "error.main" : "text.primary" }}
          />
          <StatRow label="GPS Strength" value={gpsStrength} />
          <StatRow
            label="Battery"
            value={`${batteryCellDisplay} • ${batteryHealth}`}
            valueSx={{ textAlign: "right" }}
          />
          <StatRow label="Link Quality" value={linkQuality} />
          <StatRow label="Altitude" value={altitudeDisplay} />
          <StatRow label="Wind @ Altitude" value={windDisplay} />
          <StatRow
            label="Failsafe State"
            value={failsafeState}
            valueSx={{ color: failsafeActive ? "error.main" : "text.primary" }}
          />

          <Divider sx={{ my: 0.5 }} />

          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Mission Controls
            </Typography>
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <Typography
                variant="caption"
                sx={{ fontFamily: "monospace", color: "text.secondary" }}
              >
                {flightId ? `flight ${flightId}` : "no active flight"}
              </Typography>
              {flightId && (
                <Tooltip title="View mission timeline">
                  <IconButton
                    size="small"
                    onClick={() => navigate(`/missions/${flightId}/timeline`)}
                  >
                    <TimelineIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Stack>
          </Stack>

          {!flightId && <Alert severity="info">Start a mission to enable controls.</Alert>}
          {lifecycle?.last_error && (
            <Alert severity="error">Last mission error: {lifecycle.last_error}</Alert>
          )}
          {commandError && <Alert severity="error">{commandError}</Alert>}
          {commandMessage && <Alert severity="success">{commandMessage}</Alert>}

          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="outlined"
              fullWidth
              onClick={() => issueCommand("pause")}
              disabled={!flightId || !commandCapabilities.pause || commandBusy !== null}
            >
              {commandBusy === "pause" ? <CircularProgress size={16} /> : "Pause"}
            </Button>
            <Button
              size="small"
              variant="outlined"
              fullWidth
              onClick={() => issueCommand("resume")}
              disabled={!flightId || !commandCapabilities.resume || commandBusy !== null}
            >
              {commandBusy === "resume" ? <CircularProgress size={16} /> : "Resume"}
            </Button>
            <Button
              size="small"
              color="error"
              variant="contained"
              fullWidth
              onClick={() => issueCommand("abort")}
              disabled={!flightId || !commandCapabilities.abort || commandBusy !== null}
            >
              {commandBusy === "abort" ? <CircularProgress size={16} color="inherit" /> : "Abort"}
            </Button>
          </Stack>

          <Box sx={{ pt: 0.1 }}>
            <Typography
              variant="caption"
              sx={{ display: "block", mb: 0.6, letterSpacing: 0.6, fontWeight: 700 }}
            >
              COMMAND AUDIT
            </Typography>
            {auditError && <Alert severity="warning">{auditError}</Alert>}
            {auditLoading && recentAudit.length === 0 ? (
              <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
                <CircularProgress size={18} />
              </Box>
            ) : recentAudit.length === 0 ? (
              <Typography variant="caption" color="text.secondary">
                No commands recorded for this mission yet.
              </Typography>
            ) : (
              <Table size="small" sx={{ "& .MuiTableCell-root": { fontSize: "0.72rem", py: 0.55 } }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell>Command</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Transition</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {recentAudit.map((entry) => (
                    <TableRow key={entry.command_id}>
                      <TableCell>{formatTs(entry.requested_at)}</TableCell>
                      <TableCell sx={{ textTransform: "uppercase" }}>{entry.command}</TableCell>
                      <TableCell>
                        <Tooltip title={entry.message}>
                          <Chip
                            size="small"
                            label={entry.accepted ? "accepted" : "ignored"}
                            color={entry.accepted ? "success" : "default"}
                            variant={entry.accepted ? "filled" : "outlined"}
                          />
                        </Tooltip>
                      </TableCell>
                      <TableCell>{`${entry.state_before} -> ${entry.state_after}`}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>

          <Box sx={{ pt: 0.5 }}>
            <Typography
              variant="caption"
              sx={{ display: "block", mb: 0.6, letterSpacing: 0.6, fontWeight: 700 }}
            >
              MISSION TIMELINE
            </Typography>
            {timelineError && <Alert severity="warning">{timelineError}</Alert>}
            {recentTimeline.length === 0 ? (
              <Typography variant="caption" color="text.secondary">
                Timeline entries will appear once the mission starts changing state.
              </Typography>
            ) : (
              <Stack spacing={0.9}>
                {recentTimeline.map((entry) => (
                  <Box
                    key={entry.key}
                    sx={{
                      px: 1.1,
                      py: 0.8,
                      borderRadius: 1.5,
                      border: "1px solid",
                      borderColor: "divider",
                      backgroundColor: "background.paper",
                    }}
                  >
                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                      <Stack spacing={0.3}>
                        <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                          <Chip
                            size="small"
                            label={entry.label}
                            color={entry.kind === "transition" ? stateChipColor((entry.state as MissionLifecycleState | null) ?? null) : "default"}
                            variant={entry.kind === "transition" ? "filled" : "outlined"}
                          />
                          {entry.state && (
                            <Typography variant="caption" color="text.secondary">
                              {entry.state}
                            </Typography>
                          )}
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                          {entry.detail}
                        </Typography>
                      </Stack>
                      <Typography
                        variant="caption"
                        sx={{ fontFamily: "monospace", color: "text.secondary", textAlign: "right" }}
                      >
                        {formatTs(entry.occurredAt)}
                      </Typography>
                    </Stack>
                  </Box>
                ))}
              </Stack>
            )}
          </Box>

          <Box sx={{ pt: 0.5 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.6 }}>
              <Typography
                variant="caption"
                sx={{ letterSpacing: 0.6, fontWeight: 700 }}
              >
                OPS HEALTH
              </Typography>
              <Chip
                size="small"
                label={opsHealth?.status?.toUpperCase() ?? "UNKNOWN"}
                color={opsChipColor(opsHealth?.status)}
                variant={opsHealth ? "filled" : "outlined"}
              />
            </Stack>
            {opsError && <Alert severity="warning">{opsError}</Alert>}
            {!opsHealth ? (
              <Typography variant="caption" color="text.secondary">
                Operational health is unavailable right now.
              </Typography>
            ) : (
              <Stack spacing={1}>
                <StatRow
                  label="Telemetry Feed"
                  value={
                    opsHealth.telemetry.source_connected
                      ? "Connected"
                      : opsHealth.telemetry.running
                        ? "Waiting for source"
                        : "Stopped"
                  }
                />
                <StatRow
                  label="Last Update Age"
                  value={
                    opsHealth.telemetry.last_update_age_sec == null
                      ? "--"
                      : `${opsHealth.telemetry.last_update_age_sec.toFixed(1)}s`
                  }
                  valueSx={{
                    color: opsHealth.telemetry.has_recent_update ? "success.main" : "warning.main",
                  }}
                />
                <StatRow
                  label="Video Link"
                  value={
                    !opsHealth.video.available
                      ? "Unavailable"
                      : opsHealth.video.healthy
                        ? `Healthy @ ${Math.round(opsHealth.video.fps ?? 0)} fps`
                        : "Degraded"
                  }
                  valueSx={{
                    color:
                      !opsHealth.video.available || opsHealth.video.healthy
                        ? "text.primary"
                        : "warning.main",
                  }}
                />
                <StatRow
                  label="Shadow Mode"
                  value={
                    opsHealth.shadow.shadow_mode_active
                      ? `${opsHealth.shadow.old_path.error_rate_pct}% legacy write errors`
                      : "Disabled"
                  }
                />

                <Divider sx={{ my: 0.25 }} />

                <Typography variant="caption" color="text.secondary">
                  Queue utilization
                </Typography>
                <Stack spacing={0.7}>
                  {queueRows.map(([label, queue]) => (
                    <Stack key={label} direction="row" justifyContent="space-between" spacing={1}>
                      <Typography variant="caption" color="text.secondary">
                        {label}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: "monospace",
                          color: queue.utilization_pct >= 80 ? "warning.main" : "text.primary",
                        }}
                      >
                        {queue.depth}/{queue.capacity} ({queue.utilization_pct.toFixed(0)}%)
                      </Typography>
                    </Stack>
                  ))}
                </Stack>

                {opsHealth.active_mission && (
                  <Alert severity="info" sx={{ py: 0.4 }}>
                    Active mission: {opsHealth.active_mission.mission_name} ({opsHealth.active_mission.state})
                  </Alert>
                )}

                {opsHealth.alerts.length > 0 ? (
                  <Stack spacing={0.5}>
                    {opsHealth.alerts.slice(0, 3).map((alert) => (
                      <Alert key={alert} severity="warning" sx={{ py: 0.25 }}>
                        {alert}
                      </Alert>
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    No active operational warnings.
                  </Typography>
                )}
              </Stack>
            )}
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
