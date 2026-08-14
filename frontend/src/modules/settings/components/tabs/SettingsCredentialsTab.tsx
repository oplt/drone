import { Stack, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import { OrgApiKeysPanel } from "../OrgApiKeysPanel";
import { SecretField } from "../SecretField";
import type { SettingsTabPanelProps } from "../settingsTabProps";

type SettingsCredentialsTabProps = SettingsTabPanelProps & {
  token: string | null;
  hasOrg: boolean;
};

export function SettingsCredentialsTab({
  doc,
  update,
  token,
  hasOrg,
}: SettingsCredentialsTabProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          External APIs
        </Typography>
        <Stack spacing={3}>
          <SecretField
            fullWidth
            label="Google Maps API Key"
            value={doc.credentials?.google_maps_api_key}
            onChange={(e) => update("credentials", "google_maps_api_key", e.target.value)}
          />
          <SecretField
            fullWidth
            label="Drone Connection String"
            value={doc.credentials?.drone_conn}
            onChange={(e) => update("credentials", "drone_conn", e.target.value)}
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Administration
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Admin Emails"
            value={doc.credentials?.admin_emails}
            onChange={(e) => update("credentials", "admin_emails", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Admin Domains"
            value={doc.credentials?.admin_domains}
            onChange={(e) => update("credentials", "admin_domains", e.target.value)}
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12 }}>
        <Typography variant="h6" gutterBottom>
          Organisation API Keys
        </Typography>
        <OrgApiKeysPanel token={token} hasOrg={hasOrg} />
      </Grid>
    </Grid>
  );
}
