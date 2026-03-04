import { Paper, Stack, Typography } from "@mui/material";
import { useMissionCommandMetrics } from "../../../hooks/useMissionCommandMetrics";

function StatRow({
  label,
  value,
  valueSx,
}: {
  label: string;
  value: string;
  valueSx?: any;
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

export function MissionCommandPanel({
  telemetry,
  droneConnected,
  title = "Command Panel",
  sx,
}: {
  telemetry: any;
  droneConnected: boolean;
  title?: string;
  sx?: any;
}) {
  const {
    flightStatus,
    gpsStrength,
    batteryHealth,
    failsafeState,
    batteryCellDisplay,
    linkQuality,
    windDisplay,
    failsafeActive,
  } = useMissionCommandMetrics(telemetry);

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: 2,
        borderColor: "hsla(174, 30%, 40%, 0.25)",
        background: "hsla(0, 0%, 100%, 0.7)",
        ...sx,
      }}
    >
      <Typography variant="subtitle1">{title}</Typography>
      <Stack spacing={1.2} sx={{ mt: 1 }}>
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
        <StatRow label="Wind @ Altitude" value={windDisplay} />
        <StatRow
          label="Failsafe State"
          value={failsafeState}
          valueSx={{ color: failsafeActive ? "error.main" : "text.primary" }}
        />
      </Stack>
    </Paper>
  );
}
