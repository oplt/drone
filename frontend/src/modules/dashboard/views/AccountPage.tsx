import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getToken } from "../../../modules/session";
import { fetchAccountProfile, type AccountProfile } from "../../../modules/session/api/accountApi";
import PageLayout from "../../../shared/layout/PageLayout";
import { AccountInfoSection } from "../components/AccountInfoSection";
import { AccountLoadingSkeleton } from "../components/AccountLoadingSkeleton";
import { AccountPasswordSection } from "../components/AccountPasswordSection";
import { AccountTwoFASection } from "../components/AccountTwoFASection";

export default function AccountPage() {
  const token = getToken();
  const queryClient = useQueryClient();

  const { data: user, isLoading, error } = useQuery<AccountProfile>({
    queryKey: ["me"],
    enabled: Boolean(token),
    queryFn: () => fetchAccountProfile(token),
  });

  const refreshUser = () => queryClient.invalidateQueries({ queryKey: ["me"] });

  return (
    <PageLayout
      eyebrow="Account"
      title="Security and access controls"
      description="Manage password changes, two-factor authentication, and the core account details attached to your operator access."
      metrics={[
        {
          label: "Email verification",
          value: user?.email_verified ? "Verified" : "Pending",
          caption: "Primary sign-in address",
        },
        {
          label: "Two-factor auth",
          value: user?.twofa_enabled ? "Enabled" : "Disabled",
          caption: "Authenticator protection",
        },
        {
          label: "Member since",
          value: user?.created_at ? new Date(user.created_at).toLocaleDateString() : "--",
          caption: "Account age",
        },
      ]}
    >
      {isLoading ? <AccountLoadingSkeleton /> : null}
      {error || !user ? (
        <Alert severity="error">Failed to load account information. Please refresh the page.</Alert>
      ) : null}

      {!isLoading && user ? (
        <Stack spacing={3}>
          <AccountInfoSection user={user} />
          <AccountPasswordSection token={token} />
          <AccountTwoFASection user={user} token={token} onRefreshUser={refreshUser} />
        </Stack>
      ) : null}
    </PageLayout>
  );
}
