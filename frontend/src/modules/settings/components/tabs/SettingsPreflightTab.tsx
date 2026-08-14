import { FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import type { SettingsTabPanelProps } from "../settingsTabProps";

export function SettingsPreflightTab({ doc, update }: SettingsTabPanelProps) {
  return (
    <Grid container spacing={4}>
      <Grid size={{ xs: 12, md: 3 }}>
        <Typography variant="h6" gutterBottom>
          GPS & Navigation
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="HDOP Max"
            type="number"
            value={doc.preflight?.HDOP_MAX}
            onChange={(e) => update("preflight", "HDOP_MAX", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Satellites Min"
            type="number"
            value={doc.preflight?.SAT_MIN}
            onChange={(e) => update("preflight", "SAT_MIN", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Home Max Dist (m)"
            type="number"
            value={doc.preflight?.HOME_MAX_DIST}
            onChange={(e) => update("preflight", "HOME_MAX_DIST", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="GPS Fix Type Min"
            type="number"
            value={doc.preflight?.GPS_FIX_TYPE_MIN}
            onChange={(e) => update("preflight", "GPS_FIX_TYPE_MIN", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="EKF Threshold"
            type="number"
            value={doc.preflight?.EKF_THRESHOLD}
            onChange={(e) => update("preflight", "EKF_THRESHOLD", Number(e.target.value))}
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.preflight?.COMPASS_HEALTH_REQUIRED}
                onChange={(e) =>
                  update("preflight", "COMPASS_HEALTH_REQUIRED", e.target.checked)
                }
              />
            }
            label="Compass Health Required"
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 3 }}>
        <Typography variant="h6" gutterBottom>
          Battery & Heartbeat
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Battery Min (V)"
            type="number"
            value={doc.preflight?.BATTERY_MIN_V}
            onChange={(e) => update("preflight", "BATTERY_MIN_V", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Battery Min %"
            type="number"
            value={doc.preflight?.BATTERY_MIN_PERCENT}
            onChange={(e) => update("preflight", "BATTERY_MIN_PERCENT", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Heartbeat Max Age"
            type="number"
            value={doc.preflight?.HEARTBEAT_MAX_AGE}
            onChange={(e) => update("preflight", "HEARTBEAT_MAX_AGE", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Msg Rate Min (Hz)"
            type="number"
            value={doc.preflight?.MSG_RATE_MIN_HZ}
            onChange={(e) => update("preflight", "MSG_RATE_MIN_HZ", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="RTL Min Alt (m)"
            type="number"
            value={doc.preflight?.RTL_MIN_ALT}
            onChange={(e) => update("preflight", "RTL_MIN_ALT", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Min Clearance (m)"
            type="number"
            value={doc.preflight?.MIN_CLEARANCE}
            onChange={(e) => update("preflight", "MIN_CLEARANCE", Number(e.target.value))}
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 3 }}>
        <Typography variant="h6" gutterBottom>
          Altitude & Range
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="AGL Min (m)"
            type="number"
            value={doc.preflight?.AGL_MIN}
            onChange={(e) => update("preflight", "AGL_MIN", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="AGL Max (m)"
            type="number"
            value={doc.preflight?.AGL_MAX}
            onChange={(e) => update("preflight", "AGL_MAX", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Max Range (m)"
            type="number"
            value={doc.preflight?.MAX_RANGE_M}
            onChange={(e) => update("preflight", "MAX_RANGE_M", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Max Waypoints"
            type="number"
            value={doc.preflight?.MAX_WAYPOINTS}
            onChange={(e) => update("preflight", "MAX_WAYPOINTS", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="NFZ Buffer (m)"
            type="number"
            value={doc.preflight?.NFZ_BUFFER_M}
            onChange={(e) => update("preflight", "NFZ_BUFFER_M", Number(e.target.value))}
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 3 }}>
        <Typography variant="h6" gutterBottom>
          Performance
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="A Lat Max"
            type="number"
            value={doc.preflight?.A_LAT_MAX}
            onChange={(e) => update("preflight", "A_LAT_MAX", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Bank Max (deg)"
            type="number"
            value={doc.preflight?.BANK_MAX_DEG}
            onChange={(e) => update("preflight", "BANK_MAX_DEG", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Turn Penalty (s)"
            type="number"
            value={doc.preflight?.TURN_PENALTY_S}
            onChange={(e) => update("preflight", "TURN_PENALTY_S", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="WP Radius (m)"
            type="number"
            value={doc.preflight?.WP_RADIUS_M}
            onChange={(e) => update("preflight", "WP_RADIUS_M", Number(e.target.value))}
          />
        </Stack>
      </Grid>
    </Grid>
  );
}
