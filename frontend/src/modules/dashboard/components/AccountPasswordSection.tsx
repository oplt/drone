import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import { useMutation } from "@tanstack/react-query";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { PageSection } from "../../../shared/layout/PageLayout";
import {
  updatePassword,
  type PasswordUpdatePayload,
} from "../../../modules/session/api/accountApi";
import { AccountPasswordField } from "./AccountPasswordField";

function validatePasswordChange({
  currentPassword,
  newPassword,
  confirmPassword,
}: {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}): string | null {
  if (!currentPassword) return "Please enter your current password.";
  if (newPassword.length < 8) return "New password must be at least 8 characters.";
  if (newPassword !== confirmPassword) return "New passwords do not match.";
  if (newPassword === currentPassword) return "New password must differ from current password.";
  return null;
}

export function AccountPasswordSection({ token }: { token: string | null }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mutation = useMutation({
    mutationFn: (payload: PasswordUpdatePayload) => updatePassword(payload, token),
    onSuccess: () => {
      setSuccess(true);
      setError(null);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
    onError: (err: unknown) => {
      setSuccess(false);
      setError(err instanceof Error ? err.message : "Failed to change password.");
    },
  });

  const handleSubmit = () => {
    setSuccess(false);
    const validationError = validatePasswordChange({
      currentPassword,
      newPassword,
      confirmPassword,
    });
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    mutation.mutate({
      current_password: currentPassword,
      new_password: newPassword,
      new_password_confirm: confirmPassword,
    });
  };

  return (
    <PageSection
      title="Password"
      description="Refresh your credentials without leaving the account workspace."
    >
      <Stack spacing={2.5}>
        {success ? (
          <Alert severity="success" onClose={() => setSuccess(false)}>
            Password changed successfully.
          </Alert>
        ) : null}
        {error ? (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}
        <AccountPasswordField
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
          disabled={mutation.isPending}
        />
        <AccountPasswordField
          label={<InfoLabel label="New password" info="Minimum 8 characters." />}
          inputLabelProps={{ shrink: true, sx: { pointerEvents: "auto" } }}
          value={newPassword}
          onChange={setNewPassword}
          disabled={mutation.isPending}
          error={Boolean(newPassword && newPassword.length < 8)}
        />
        <AccountPasswordField
          label="Confirm new password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          disabled={mutation.isPending}
          error={Boolean(confirmPassword && newPassword !== confirmPassword)}
          helperText={
            confirmPassword && newPassword !== confirmPassword ? "Passwords do not match." : undefined
          }
        />
        <Box>
          <ActionIconButton
            variant="upgrade"
            title={mutation.isPending ? "Updating…" : "Change password"}
            color="primary"
            loading={mutation.isPending}
            disabled={mutation.isPending}
            onClick={handleSubmit}
          />
        </Box>
      </Stack>
    </PageSection>
  );
}
