import { FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import type { SettingsTabPanelProps } from "../settingsTabProps";

export function SettingsHardwareTab({ doc, update }: SettingsTabPanelProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Drone
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Battery Capacity (Wh)"
            type="number"
            value={doc.hardware?.battery_capacity_wh}
            onChange={(e) => update("hardware", "battery_capacity_wh", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Energy Reserve Fraction"
            type="number"
            inputProps={{ step: 0.1, min: 0, max: 1 }}
            value={doc.hardware?.energy_reserve_frac}
            onChange={(e) => update("hardware", "energy_reserve_frac", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Cruise Power (W)"
            type="number"
            value={doc.hardware?.cruise_power_w}
            onChange={(e) => update("hardware", "cruise_power_w", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Cruise Speed (mps)"
            type="number"
            value={doc.hardware?.cruise_speed_mps}
            onChange={(e) => update("hardware", "cruise_speed_mps", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Heartbeat Timeout"
            type="number"
            value={doc.hardware?.heartbeat_timeout}
            onChange={(e) => update("hardware", "heartbeat_timeout", Number(e.target.value))}
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.hardware?.enforce_preflight_range}
                onChange={(e) =>
                  update("hardware", "enforce_preflight_range", e.target.checked)
                }
              />
            }
            label="Enforce Preflight Range"
          />
        </Stack>
      </Grid>
    </Grid>
  );
}
