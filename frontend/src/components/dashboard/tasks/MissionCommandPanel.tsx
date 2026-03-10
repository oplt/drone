import { useCallback, useEffect, useMemo, useState } from "react";
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
import { getToken } from "../../../auth";
import { useMissionCommandMetrics } from "../../../hooks/useMissionCommandMetrics";
import {
  getMissionCommandAudit,
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
  return new Date(unixSeconds * 1000).toLocaleTimeString();
};

const toMessage = (error: unknown): string =>
  error instanceof Error ? error.message : "Command request failed";

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
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
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

  useEffect(() => {
    void loadAudit();
  }, [loadAudit]);

  useEffect(() => {
    if (!flightId || !apiBase) return;
    const handle = window.setInterval(() => {
      void loadAudit();
    }, 12000);
    return () => window.clearInterval(handle);
  }, [apiBase, flightId, loadAudit]);

  const recentAudit = useMemo(
    () => [...audit].sort((a, b) => b.requested_at - a.requested_at).slice(0, 8),
    [audit],
  );

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
      } catch (error) {
        setCommandError(toMessage(error));
      } finally {
        setCommandBusy(null);
      }
    },
    [apiBase, buildIdempotencyKey, flightId, getTokenFn, loadAudit],
  );

  return (
    <Accordion
      disableGutters
      defaultExpanded={defaultExpanded}
      sx={{
        borderRadius: 2,
        border: "1px solid",
        borderColor: "hsla(174, 30%, 40%, 0.25)",
        background: "hsla(0, 0%, 100%, 0.7)",
        "&:before": { display: "none" },
        ...sx,
      }}
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

      <AccordionDetails sx={{ px: 2, pb: 2, pt: 0.5 }}>
        <Stack spacing={1.2}>
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
            <Typography
              variant="caption"
              sx={{ fontFamily: "monospace", color: "text.secondary" }}
            >
              {flightId ? `flight ${flightId}` : "no active flight"}
            </Typography>
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

          <Box sx={{ pt: 0.5 }}>
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
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
