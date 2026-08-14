import { Stack, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import { ActionIconLabel } from "../../../../shared/ui/ActionIconButton";
import { SecretField } from "../SecretField";
import type { SettingsFileUploadTabProps } from "../settingsTabProps";
import { SETTINGS_MASK } from "../../settingsDefaults";

export function SettingsRaspberryTab({
  doc,
  update,
  onFileUpload,
}: SettingsFileUploadTabProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Raspberry Pi Connection
        </Typography>
        <Stack spacing={3}>
          <SecretField
            fullWidth
            label="IP Address"
            value={doc.raspberry?.raspberry_ip}
            onChange={(e) => update("raspberry", "raspberry_ip", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Hostname"
            value={doc.raspberry?.raspberry_host}
            onChange={(e) => update("raspberry", "raspberry_host", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Username"
            value={doc.raspberry?.raspberry_user}
            onChange={(e) => update("raspberry", "raspberry_user", e.target.value)}
          />
          <SecretField
            fullWidth
            label="Password"
            placeholder={SETTINGS_MASK}
            value={doc.raspberry?.raspberry_password}
            onChange={(e) => update("raspberry", "raspberry_password", e.target.value)}
          />
          <SecretField
            fullWidth
            label="Streaming Script Path"
            value={doc.raspberry?.raspberry_streaming_script_path}
            onChange={(e) =>
              update("raspberry", "raspberry_streaming_script_path", e.target.value)
            }
          />
          <ActionIconLabel variant="upload" title="Upload SSH Key">
            <input
              type="file"
              hidden
              accept=".pem,.key,.pub"
              onChange={onFileUpload("raspberry", "ssh_key_path")}
            />
          </ActionIconLabel>
          {doc.raspberry?.ssh_key_path && (
            <Typography variant="caption" display="block" sx={{ mt: 1 }}>
              ✓ SSH key uploaded
            </Typography>
          )}
        </Stack>
      </Grid>
    </Grid>
  );
}
