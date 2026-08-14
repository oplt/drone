import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useMutation } from "@tanstack/react-query";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { PageSection } from "../../../shared/layout/PageLayout";
import {
  disableTwoFactor,
  setupTwoFactor,
  verifyTwoFactor,
  type AccountProfile,
  type TwoFactorSetup,
  type TwoFactorVerifyPayload,
} from "../../../modules/session/api/accountApi";
import { AccountPasswordField } from "./AccountPasswordField";

export function AccountTwoFASection({
  user,
  token,
  onRefreshUser,
}: {
  user: AccountProfile;
  token: string | null;
  onRefreshUser: () => void;
}) {
  const [setupData, setSetupData] = useState<TwoFactorSetup | null>(null);
  const [verifyToken, setVerifyToken] = useState("");
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [verifySuccess, setVerifySuccess] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableError, setDisableError] = useState<string | null>(null);

  const setupMutation = useMutation({
    mutationFn: () => setupTwoFactor(token),
    onSuccess: (data) => {
      setSetupData(data);
      setVerifyToken("");
      setVerifyError(null);
    },
  });

  const verifyMutation = useMutation({
    mutationFn: (payload: TwoFactorVerifyPayload) => verifyTwoFactor(payload, token),
    onSuccess: () => {
      setVerifySuccess(true);
      setVerifyError(null);
      setSetupData(null);
      onRefreshUser();
    },
    onError: () => setVerifyError("Invalid code. Please try again."),
  });

  const disableMutation = useMutation({
    mutationFn: (payload: { password: string }) => disableTwoFactor(payload, token),
    onSuccess: () => {
      setDisableOpen(false);
      setDisablePassword("");
      setDisableError(null);
      onRefreshUser();
    },
    onError: () => setDisableError("Incorrect password. Please try again."),
  });

  const handleVerify = () => {
    if (verifyToken.length !== 6) {
      setVerifyError("Enter the 6-digit code.");
      return;
    }
    verifyMutation.mutate({ token: verifyToken, secret: setupData?.secret });
  };

  return (
    <PageSection
      title="Two-factor authentication"
      description="Add an authenticator app step to protect account access and mission controls."
      action={
        <Chip
          size="small"
          label={user.twofa_enabled ? "Enabled" : "Disabled"}
          color={user.twofa_enabled ? "success" : "default"}
        />
      }
    >
      <Stack spacing={2.5}>
        {verifySuccess ? (
          <Alert severity="success" onClose={() => setVerifySuccess(false)}>
            Two-factor authentication enabled.
          </Alert>
        ) : null}

        {!user.twofa_enabled && !setupData ? (
          <Box>
            <ActionIconButton
              variant="preflight"
              title={setupMutation.isPending ? "Setting up…" : "Set up 2FA"}
              loading={setupMutation.isPending}
              disabled={setupMutation.isPending}
              onClick={() => setupMutation.mutate()}
            />
          </Box>
        ) : null}

        {!user.twofa_enabled && setupData ? (
          <Stack spacing={2}>
            <Typography variant="body2">
              Scan this QR code with your authenticator app, then enter the 6-digit code below to
              confirm.
            </Typography>
            <Box>
              <img
                src={`data:image/png;base64,${setupData.qr_code}`}
                alt="2FA QR code"
                style={{ width: 180, height: 180, border: "1px solid #e0e0e0", borderRadius: 12 }}
              />
            </Box>
            <Typography variant="body2" color="text.secondary" fontFamily="monospace">
              Manual key: {setupData.secret}
            </Typography>
            <TextField
              label="Verification code"
              value={verifyToken}
              onChange={(event) =>
                setVerifyToken(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
              slotProps={{ htmlInput: { inputMode: "numeric", maxLength: 6 } }}
              placeholder="000000"
              sx={{ maxWidth: 220 }}
              error={Boolean(verifyError)}
              helperText={verifyError ?? undefined}
              variant="filled"
            />
            <Stack direction="row" spacing={0.25}>
              <ActionIconButton
                variant="check"
                title={verifyMutation.isPending ? "Verifying…" : "Verify & enable"}
                color="primary"
                loading={verifyMutation.isPending}
                disabled={verifyMutation.isPending || verifyToken.length !== 6}
                onClick={handleVerify}
              />
              <ActionIconButton
                variant="close"
                title="Cancel"
                onClick={() => setSetupData(null)}
              />
            </Stack>
          </Stack>
        ) : null}

        {user.twofa_enabled ? (
          <Box>
            <ActionIconButton
              variant="delete"
              title="Disable 2FA"
              color="error"
              onClick={() => setDisableOpen(true)}
            />
          </Box>
        ) : null}
      </Stack>

      <Dialog open={disableOpen} onClose={() => setDisableOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Disable two-factor authentication</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Enter your password to confirm you want to disable 2FA.
          </DialogContentText>
          {disableError ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {disableError}
            </Alert>
          ) : null}
          <AccountPasswordField
            label="Password"
            value={disablePassword}
            onChange={setDisablePassword}
            disabled={disableMutation.isPending}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5 }}>
          <ActionIconButton
            variant="close"
            title="Cancel"
            onClick={() => {
              setDisableOpen(false);
              setDisablePassword("");
              setDisableError(null);
            }}
          />
          <ActionIconButton
            variant="delete"
            title={disableMutation.isPending ? "Disabling…" : "Disable"}
            color="error"
            loading={disableMutation.isPending}
            disabled={disableMutation.isPending || !disablePassword}
            onClick={() => disableMutation.mutate({ password: disablePassword })}
          />
        </DialogActions>
      </Dialog>
    </PageSection>
  );
}
