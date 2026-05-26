import { Divider, Stack } from "@mui/material";
import { useMissionCommandMetrics } from "../../../../modules/mission-runtime";
import { StatRow } from "./StatRow";

export function CommandMetricsSection({
  telemetry,
  droneConnected,
}: {
  telemetry: unknown;
  droneConnected: boolean;
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

  return (
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
    </Stack>
  );
}
