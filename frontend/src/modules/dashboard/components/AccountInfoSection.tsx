import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";

import { PageSection } from "../../../shared/layout/PageLayout";
import type { AccountProfile } from "../../../modules/session/api/accountApi";

export function AccountInfoSection({ user }: { user: AccountProfile }) {
  return (
    <PageSection
      title="Account information"
      description="Read-only account metadata used throughout the workspace."
    >
      <Stack spacing={1.5}>
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="body2" color="text.secondary">
            Email
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2">{user.email}</Typography>
            {user.email_verified ? (
              <Chip size="small" label="Verified" color="success" variant="outlined" />
            ) : null}
          </Stack>
        </Stack>
        <Divider />
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="body2" color="text.secondary">
            Member since
          </Typography>
          <Typography variant="body2">{new Date(user.created_at).toLocaleDateString()}</Typography>
        </Stack>
      </Stack>
    </PageSection>
  );
}
