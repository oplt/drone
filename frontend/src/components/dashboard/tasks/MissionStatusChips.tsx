import { Chip, Stack } from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";

export function MissionStatusChips({
  droneConnected,
  wsConnected,
  sx,
}: {
  droneConnected: boolean;
  wsConnected: boolean;
  sx?: SxProps<Theme>;
}) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={sx}>
      <Chip
        size="small"
        label={droneConnected ? "Drone online" : "Drone offline"}
        color={droneConnected ? "success" : "default"}
        variant={droneConnected ? "filled" : "outlined"}
      />
      <Chip
        size="small"
        label={wsConnected ? "Secure link" : "Link down"}
        color={wsConnected ? "success" : "default"}
        variant={wsConnected ? "filled" : "outlined"}
      />
    </Stack>
  );
}
