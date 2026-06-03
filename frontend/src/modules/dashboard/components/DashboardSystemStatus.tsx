import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { PageSection } from "../../../shared/layout/PageLayout";

type DashboardSystemStatusProps = {
  telemetryRunning?: boolean;
  mavlinkConnected?: boolean;
  activeConnections?: number;
  lastUpdateAge: number | null;
};

function StatusRow({
  label,
  value,
  tooltip,
}: {
  label: string;
  value: string | number;
  tooltip: string;
}) {
  return (
    <Tooltip title={tooltip} arrow>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {value}
        </Typography>
      </Stack>
    </Tooltip>
  );
}

export default function DashboardSystemStatus({
  telemetryRunning,
  mavlinkConnected,
  activeConnections = 0,
  lastUpdateAge,
}: DashboardSystemStatusProps) {
  return (
    <PageSection title="System status">
      <Stack spacing={1}>
        <StatusRow
          label="WebSocket"
          value={telemetryRunning ? "Running" : "Stopped"}
          tooltip="Backend telemetry websocket broadcaster state."
        />
        <StatusRow
          label="Clients"
          value={activeConnections}
          tooltip="Connected dashboard/operator sessions."
        />
        <StatusRow
          label="MAVLink"
          value={mavlinkConnected ? "Connected" : "Idle"}
          tooltip="Vehicle transport connection state."
        />
        <StatusRow
          label="Last telemetry"
          value={lastUpdateAge !== null ? `${lastUpdateAge}s ago` : "--"}
          tooltip="Time since latest telemetry heartbeat."
        />
      </Stack>
    </PageSection>
  );
}
