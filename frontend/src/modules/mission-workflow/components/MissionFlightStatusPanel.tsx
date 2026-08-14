import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import { deriveTelemetry } from "../../mission-runtime/utils/deriveTelemetry";
import type { MissionStatus } from "../types";

export function MissionFlightStatusPanel({
  missionStatus,
  wsConnected,
  lastPacketAgeSec = null,
}: {
  missionStatus: MissionStatus;
  wsConnected?: boolean;
  /** Seconds since last telemetry packet; null when unknown. */
  lastPacketAgeSec?: number | null;
}) {
  const derived = deriveTelemetry(missionStatus.telemetry);
  const droneOnline = Boolean(missionStatus.orchestrator?.drone_connected);
  const linkUp =
    wsConnected ?? Boolean(missionStatus.telemetry?.running);
  const linkColor = linkUp ? "success" : "error";
  const modeLabel = derived.modeShort !== "--" ? derived.modeShort : "—";
  const gpsLabel =
    derived.sats != null
      ? `${derived.sats} sats${derived.hdop != null ? ` · HDOP ${derived.hdop.toFixed(1)}` : ""}`
      : derived.gpsStrength ?? "GPS —";

  return (
    <Paper variant="outlined" sx={{ mt: 2, p: 2, borderRadius: 2 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.25 }}>
        Flight status
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.25 }}>
        <Chip
          size="small"
          label={droneOnline ? "Drone online" : "Drone offline"}
          color={droneOnline ? "success" : "warning"}
          variant={droneOnline ? "filled" : "outlined"}
        />
        <Chip
          size="small"
          label={linkUp ? "Link up" : "Link down"}
          color={linkColor}
          variant={linkUp ? "filled" : "outlined"}
        />
        <Chip size="small" label={`Mode ${modeLabel}`} variant="outlined" />
        <Chip size="small" label={gpsLabel} variant="outlined" />
        {derived.batteryPct != null ? (
          <Chip
            size="small"
            label={`BAT ${derived.batteryPct}%`}
            color={derived.batteryPct < 30 ? "error" : "default"}
            variant="outlined"
          />
        ) : null}
      </Stack>
      <Stack spacing={0.5}>
        {missionStatus.flight_id ? (
          <Typography variant="caption" color="text.secondary">
            Flight {missionStatus.flight_id}
          </Typography>
        ) : null}
        {missionStatus.mission_name ? (
          <Typography variant="caption" color="text.secondary">
            Plan {missionStatus.mission_name}
          </Typography>
        ) : null}
        <Typography variant="caption" color="text.secondary">
          Operator sessions:{" "}
          {missionStatus.telemetry?.active_connections ?? "—"}
          {lastPacketAgeSec != null ? ` · last packet ${lastPacketAgeSec}s ago` : ""}
        </Typography>
      </Stack>
    </Paper>
  );
}
