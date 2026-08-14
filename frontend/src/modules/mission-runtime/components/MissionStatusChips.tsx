import { Chip, Stack } from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import { deriveTelemetry } from "../utils/deriveTelemetry";

export function MissionStatusChips({
  droneConnected,
  wsConnected,
  telemetry,
  sx,
}: {
  droneConnected: boolean;
  wsConnected: boolean;
  telemetry?: unknown;
  sx?: SxProps<Theme>;
}) {
  const derived = deriveTelemetry(telemetry);
  const batteryLabel = derived.batteryShort;
  const modeLabel = derived.modeShort !== "--" ? derived.modeShort : "MODE --";
  const gpsLabel = derived.gpsShort;
  const freshnessLabel = wsConnected ? "Link up" : "Link down";
  const batteryWarn =
    derived.batteryPct != null && derived.batteryPct < 30
      ? ("warning" as const)
      : undefined;
  const batteryError =
    derived.batteryPct != null && derived.batteryPct < 15
      ? ("error" as const)
      : undefined;

  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      flexWrap="wrap"
      useFlexGap
      sx={sx}
      role="status"
      aria-label="Mission status"
    >
      <Chip
        size="small"
        label={droneConnected ? "Drone online" : "Drone offline"}
        color={droneConnected ? "success" : "warning"}
        variant={droneConnected ? "filled" : "outlined"}
      />
      <Chip
        size="small"
        label={freshnessLabel}
        color={wsConnected ? "success" : "error"}
        variant={wsConnected ? "filled" : "outlined"}
      />
      <Chip
        size="small"
        label={batteryLabel}
        color={batteryError ?? batteryWarn}
        variant="outlined"
      />
      <Chip size="small" label={gpsLabel} variant="outlined" />
      <Chip size="small" label={modeLabel} variant="outlined" />
    </Stack>
  );
}
