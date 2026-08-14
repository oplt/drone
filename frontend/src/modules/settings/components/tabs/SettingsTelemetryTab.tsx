import {
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid";
import { ActionIconLabel } from "../../../../shared/ui/ActionIconButton";
import { SecretField } from "../SecretField";
import type { SettingsFileUploadTabProps } from "../settingsTabProps";
import { SETTINGS_MASK } from "../../settingsDefaults";

export function SettingsTelemetryTab({
  doc,
  update,
  onFileUpload,
}: SettingsFileUploadTabProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 4 }}>
        <Typography variant="h6" gutterBottom>
          MQTT Broker
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Broker"
            value={doc.telemetry?.mqtt_broker}
            onChange={(e) => update("telemetry", "mqtt_broker", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Port"
            type="number"
            value={doc.telemetry?.mqtt_port}
            onChange={(e) => update("telemetry", "mqtt_port", Number(e.target.value))}
          />
          <TextField
            variant="filled"
            fullWidth
            label="User"
            value={doc.telemetry?.mqtt_user}
            onChange={(e) => update("telemetry", "mqtt_user", e.target.value)}
          />
          <SecretField
            fullWidth
            label="Password"
            placeholder={SETTINGS_MASK}
            value={doc.telemetry?.mqtt_pass}
            onChange={(e) => update("telemetry", "mqtt_pass", e.target.value)}
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.telemetry?.mqtt_use_tls}
                onChange={(e) => update("telemetry", "mqtt_use_tls", e.target.checked)}
              />
            }
            label="Use TLS"
          />
          <ActionIconLabel variant="upload" title="Upload CA Certificate">
            <input
              type="file"
              hidden
              accept=".pem,.crt,.ca"
              onChange={onFileUpload("telemetry", "mqtt_ca_certs")}
            />
          </ActionIconLabel>
          {doc.telemetry?.mqtt_ca_certs && (
            <Typography variant="caption" display="block" sx={{ mt: 1 }}>
              ✓ CA certificate uploaded
            </Typography>
          )}
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <Typography variant="h6" gutterBottom>
          OPC UA
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Endpoint"
            value={doc.telemetry?.opcua_endpoint}
            onChange={(e) => update("telemetry", "opcua_endpoint", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Security Policy"
            value={doc.telemetry?.opcua_security_policy}
            onChange={(e) => update("telemetry", "opcua_security_policy", e.target.value)}
          />
          <ActionIconLabel variant="upload" title="Upload OPC UA Certificate">
            <input
              type="file"
              hidden
              accept=".pem,.crt,.cert"
              onChange={onFileUpload("telemetry", "opcua_cert_path")}
            />
          </ActionIconLabel>
          {doc.telemetry?.opcua_cert_path && (
            <Typography variant="caption" display="block" sx={{ mt: 1 }}>
              ✓ Certificate uploaded
            </Typography>
          )}
          <ActionIconLabel variant="upload" title="Upload OPC UA Key">
            <input
              type="file"
              hidden
              accept=".pem,.key"
              onChange={onFileUpload("telemetry", "opcua_key_path")}
            />
          </ActionIconLabel>
          {doc.telemetry?.opcua_key_path && (
            <Typography variant="caption" display="block" sx={{ mt: 1 }}>
              ✓ Key uploaded
            </Typography>
          )}
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <Typography variant="h6" gutterBottom>
          Logging & Topics
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Log Interval (sec)"
            type="number"
            value={doc.telemetry?.telem_log_interval_sec}
            onChange={(e) =>
              update("telemetry", "telem_log_interval_sec", Number(e.target.value))
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Telemetry Topic"
            value={doc.telemetry?.telemetry_topic}
            onChange={(e) => update("telemetry", "telemetry_topic", e.target.value)}
          />
        </Stack>
      </Grid>
    </Grid>
  );
}
