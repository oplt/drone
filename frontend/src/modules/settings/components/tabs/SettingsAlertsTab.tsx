import { FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import { SecretField } from "../SecretField";
import type { SettingsTabPanelProps } from "../settingsTabProps";
import { SETTINGS_MASK } from "../../settingsDefaults";

export function SettingsAlertsTab({ doc, update }: SettingsTabPanelProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Rules
        </Typography>
        <Stack spacing={3}>
          <FormControlLabel
            control={
              <Switch
                checked={doc.alerts?.enabled}
                onChange={(e) => update("alerts", "enabled", e.target.checked)}
              />
            }
            label="Enable Alert Engine"
          />
          <TextField
            variant="filled"
            fullWidth
            label="Check Interval (sec)"
            type="number"
            value={doc.alerts?.check_interval_sec}
            onChange={(e) => update("alerts", "check_interval_sec", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Dedupe Window (sec)"
            type="number"
            value={doc.alerts?.dedupe_window_sec}
            onChange={(e) => update("alerts", "dedupe_window_sec", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Operation Geofence ID"
            type="number"
            value={doc.alerts?.operation_geofence_id ?? ""}
            onChange={(e) =>
              update(
                "alerts",
                "operation_geofence_id",
                e.target.value ? Number(e.target.value) : null,
              )
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Monitor Herd IDs (comma-separated)"
            value={doc.alerts?.monitor_herd_ids}
            onChange={(e) => update("alerts", "monitor_herd_ids", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Herd Isolation Threshold (m)"
            type="number"
            value={doc.alerts?.herd_isolation_threshold_m}
            onChange={(e) =>
              update("alerts", "herd_isolation_threshold_m", Number(e.target.value))
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Low Battery Threshold (%)"
            type="number"
            value={doc.alerts?.low_battery_percent}
            onChange={(e) => update("alerts", "low_battery_percent", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Weak Link Threshold (%)"
            type="number"
            value={doc.alerts?.weak_link_percent}
            onChange={(e) => update("alerts", "weak_link_percent", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="High Wind Threshold (m/s)"
            type="number"
            value={doc.alerts?.high_wind_mps}
            onChange={(e) => update("alerts", "high_wind_mps", Number(e.target.value))}
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Routing & Channels
        </Typography>
        <Stack spacing={3}>
          <FormControlLabel
            control={
              <Switch
                checked={doc.alerts?.route_in_app}
                onChange={(e) => update("alerts", "route_in_app", e.target.checked)}
              />
            }
            label="Route In-App"
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.alerts?.route_email}
                onChange={(e) => update("alerts", "route_email", e.target.checked)}
              />
            }
            label="Route Email"
          />
          <TextField
            variant="filled"
            fullWidth
            label="Email Recipients"
            value={doc.alerts?.email_recipients}
            onChange={(e) => update("alerts", "email_recipients", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="SMTP Host"
            value={doc.alerts?.smtp_host}
            onChange={(e) => update("alerts", "smtp_host", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="SMTP Port"
            type="number"
            value={doc.alerts?.smtp_port}
            onChange={(e) => update("alerts", "smtp_port", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="SMTP User"
            value={doc.alerts?.smtp_user}
            onChange={(e) => update("alerts", "smtp_user", e.target.value)}
          />
          <SecretField
            fullWidth
            label="SMTP Password"
            placeholder={SETTINGS_MASK}
            value={doc.alerts?.smtp_password}
            onChange={(e) => update("alerts", "smtp_password", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="SMTP From Address"
            value={doc.alerts?.smtp_from}
            onChange={(e) => update("alerts", "smtp_from", e.target.value)}
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.alerts?.smtp_use_tls}
                onChange={(e) => update("alerts", "smtp_use_tls", e.target.checked)}
              />
            }
            label="SMTP TLS"
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.alerts?.route_sms}
                onChange={(e) => update("alerts", "route_sms", e.target.checked)}
              />
            }
            label="Route SMS"
          />
          <TextField
            variant="filled"
            fullWidth
            label="SMS Recipients"
            value={doc.alerts?.sms_recipients}
            onChange={(e) => update("alerts", "sms_recipients", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Twilio Account SID"
            value={doc.alerts?.twilio_account_sid}
            onChange={(e) => update("alerts", "twilio_account_sid", e.target.value)}
          />
          <SecretField
            fullWidth
            label="Twilio Auth Token"
            placeholder={SETTINGS_MASK}
            value={doc.alerts?.twilio_auth_token}
            onChange={(e) => update("alerts", "twilio_auth_token", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Twilio From Number"
            value={doc.alerts?.twilio_from_number}
            onChange={(e) => update("alerts", "twilio_from_number", e.target.value)}
          />
        </Stack>
      </Grid>
    </Grid>
  );
}
