import FlightTakeoffRoundedIcon from "@mui/icons-material/FlightTakeoffRounded";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { DeviceItem } from "../../types";
import { deviceStatusColor } from "../../utils/fleetDeviceStatus";

type DeviceRowProps = {
  device: DeviceItem;
};

export function DeviceRow({ device }: DeviceRowProps) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderRadius: 3, display: "flex", alignItems: "center", gap: 2 }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="body1" fontWeight={600} noWrap>
            {device.device_name}
          </Typography>
          <Chip label={device.status} size="small" color={deviceStatusColor(device.status)} />
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block">
          {device.device_id}
        </Typography>
        {(device.last_inspection_at || device.next_inspection_due) && (
          <Typography variant="caption" color="text.secondary">
            {device.last_inspection_at
              ? `Last inspected ${new Date(device.last_inspection_at).toLocaleDateString()}`
              : ""}
            {device.last_inspection_at && device.next_inspection_due ? " · " : ""}
            {device.next_inspection_due
              ? `Next due ${new Date(device.next_inspection_due).toLocaleDateString()}`
              : ""}
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
