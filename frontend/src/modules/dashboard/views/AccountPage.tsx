import * as React from 'react';
import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import LockRoundedIcon from '@mui/icons-material/LockRounded';
import ShieldRoundedIcon from '@mui/icons-material/ShieldRounded';
import VisibilityRoundedIcon from '@mui/icons-material/VisibilityRounded';
import VisibilityOffRoundedIcon from '@mui/icons-material/VisibilityOffRounded';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getToken } from "../../../modules/session";
import {
  disableTwoFactor,
  fetchAccountProfile,
  setupTwoFactor,
  updatePassword,
  verifyTwoFactor,
  type AccountProfile,
  type PasswordUpdatePayload,
  type TwoFactorSetup,
  type TwoFactorVerifyPayload,
} from "../../../modules/session/api/accountApi";
import InfoLabel from "../../../shared/ui/InfoLabel";
import Header from "../../../shared/layout/WorkflowHeader";
import PageLayout, { PageSection } from "../../../shared/layout/PageLayout";

function PasswordField({
  label,
  value,
  onChange,
  disabled,
  helperText,
  error,
  inputLabelProps,
}: {
  label: React.ReactNode;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  helperText?: string;
  error?: boolean;
  inputLabelProps?: React.ComponentProps<typeof TextField>['InputLabelProps'];
}) {
  const [show, setShow] = useState(false);
  return (
    <TextField
      fullWidth
      label={label}
      type={show ? 'text' : 'password'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      helperText={helperText}
      error={error}
      InputLabelProps={inputLabelProps}
      variant="filled"
      slotProps={{
        input: {
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={() => setShow((current) => !current)}
                edge="end"
                tabIndex={-1}
                aria-label={show ? 'Hide password' : 'Show password'}
              >
                {show ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
              </IconButton>
            </InputAdornment>
          ),
        },
      }}
    />
  );
}

function LoadingSkeleton() {
  return (
    <Stack spacing={3}>
      <Skeleton variant="rounded" height={220} />
      <Skeleton variant="rounded" height={280} />
      <Skeleton variant="rounded" height={320} />
    </Stack>
  );
}

function PasswordSection({ token }: { token: string | null }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mutation = useMutation({
    mutationFn: (payload: PasswordUpdatePayload) => updatePassword(payload, token),
    onSuccess: () => {
      setSuccess(true);
      setError(null);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    },
    onError: (err: unknown) => {
      setSuccess(false);
      setError(err instanceof Error ? err.message : 'Failed to change password.');
    },
  });

  const validate = (): string | null => {
    if (!currentPassword) return 'Please enter your current password.';
    if (newPassword.length < 8) return 'New password must be at least 8 characters.';
    if (newPassword !== confirmPassword) return 'New passwords do not match.';
    if (newPassword === currentPassword) return 'New password must differ from current password.';
    return null;
  };

  const handleSubmit = () => {
    setSuccess(false);
    const validationError = validate();
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
    <PageSection title="Password" description="Refresh your credentials without leaving the account workspace.">
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
        <PasswordField
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
          disabled={mutation.isPending}
        />
        <PasswordField
          label={<InfoLabel label="New password" info="Minimum 8 characters." />}
          inputLabelProps={{ shrink: true, sx: { pointerEvents: 'auto' } }}
          value={newPassword}
          onChange={setNewPassword}
          disabled={mutation.isPending}
          error={Boolean(newPassword && newPassword.length < 8)}
        />
        <PasswordField
          label="Confirm new password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          disabled={mutation.isPending}
          error={Boolean(confirmPassword && newPassword !== confirmPassword)}
          helperText={
            confirmPassword && newPassword !== confirmPassword ? 'Passwords do not match.' : undefined
          }
        />
        <Box>
          <Button variant="contained" onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? 'Updating...' : 'Change password'}
          </Button>
        </Box>
      </Stack>
    </PageSection>
  );
}

function TwoFASection({
  user,
  token,
  onRefreshUser,
}: {
  user: AccountProfile;
  token: string | null;
  onRefreshUser: () => void;
}) {
  const [setupData, setSetupData] = useState<TwoFactorSetup | null>(null);
  const [verifyToken, setVerifyToken] = useState('');
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [verifySuccess, setVerifySuccess] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableError, setDisableError] = useState<string | null>(null);

  const setupMutation = useMutation({
    mutationFn: () => setupTwoFactor(token),
    onSuccess: (data) => {
      setSetupData(data);
      setVerifyToken('');
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
    onError: () => setVerifyError('Invalid code. Please try again.'),
  });

  const disableMutation = useMutation({
    mutationFn: (payload: { password: string }) => disableTwoFactor(payload, token),
    onSuccess: () => {
      setDisableOpen(false);
      setDisablePassword('');
      setDisableError(null);
      onRefreshUser();
    },
    onError: () => setDisableError('Incorrect password. Please try again.'),
  });

  const handleVerify = () => {
    if (verifyToken.length !== 6) {
      setVerifyError('Enter the 6-digit code.');
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
          label={user.twofa_enabled ? 'Enabled' : 'Disabled'}
          color={user.twofa_enabled ? 'success' : 'default'}
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
            <Button
              variant="outlined"
              onClick={() => setupMutation.mutate()}
              disabled={setupMutation.isPending}
              startIcon={<ShieldRoundedIcon fontSize="small" />}
            >
              {setupMutation.isPending ? 'Setting up...' : 'Set up 2FA'}
            </Button>
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
                style={{ width: 180, height: 180, border: '1px solid #e0e0e0', borderRadius: 12 }}
              />
            </Box>
            <Typography variant="body2" color="text.secondary" fontFamily="monospace">
              Manual key: {setupData.secret}
            </Typography>
            <TextField
              label="Verification code"
              value={verifyToken}
              onChange={(event) =>
                setVerifyToken(event.target.value.replace(/\D/g, '').slice(0, 6))
              }
              slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 6 } }}
              placeholder="000000"
              sx={{ maxWidth: 220 }}
              error={Boolean(verifyError)}
              helperText={verifyError ?? undefined}
              variant="filled"
            />
            <Stack direction="row" spacing={1.5}>
              <Button
                variant="contained"
                onClick={handleVerify}
                disabled={verifyMutation.isPending || verifyToken.length !== 6}
              >
                {verifyMutation.isPending ? 'Verifying...' : 'Verify & enable'}
              </Button>
              <Button variant="text" onClick={() => setSetupData(null)}>
                Cancel
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {user.twofa_enabled ? (
          <Box>
            <Button
              variant="outlined"
              color="error"
              startIcon={<LockRoundedIcon fontSize="small" />}
              onClick={() => setDisableOpen(true)}
            >
              Disable 2FA
            </Button>
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
          <PasswordField
            label="Password"
            value={disablePassword}
            onChange={setDisablePassword}
            disabled={disableMutation.isPending}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5 }}>
          <Button
            onClick={() => {
              setDisableOpen(false);
              setDisablePassword('');
              setDisableError(null);
            }}
          >
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={disableMutation.isPending || !disablePassword}
            onClick={() => disableMutation.mutate({ password: disablePassword })}
          >
            {disableMutation.isPending ? 'Disabling...' : 'Disable'}
          </Button>
        </DialogActions>
      </Dialog>
    </PageSection>
  );
}

function AccountInfoSection({ user }: { user: AccountProfile }) {
  return (
    <PageSection title="Account information" description="Read-only account metadata used throughout the workspace.">
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

export default function AccountPage() {
  const token = getToken();
  const queryClient = useQueryClient();

  const { data: user, isLoading, error } = useQuery<AccountProfile>({
    queryKey: ['me'],
    enabled: Boolean(token),
    queryFn: () => fetchAccountProfile(token),
  });

  const refreshUser = () => queryClient.invalidateQueries({ queryKey: ['me'] });

  return (
    <>
      <Header />
      <PageLayout
        eyebrow="Account"
        title="Security and access controls"
        description="Manage password changes, two-factor authentication, and the core account details attached to your operator access."
        metrics={[
          {
            label: 'Email verification',
            value: user?.email_verified ? 'Verified' : 'Pending',
            caption: 'Primary sign-in address',
          },
          {
            label: 'Two-factor auth',
            value: user?.twofa_enabled ? 'Enabled' : 'Disabled',
            caption: 'Authenticator protection',
          },
          {
            label: 'Member since',
            value: user?.created_at ? new Date(user.created_at).toLocaleDateString() : '--',
            caption: 'Account age',
          },
        ]}
      >
        {isLoading ? <LoadingSkeleton /> : null}
        {error || !user ? (
          <Alert severity="error">Failed to load account information. Please refresh the page.</Alert>
        ) : null}

        {!isLoading && user ? (
          <Stack spacing={3}>
            <AccountInfoSection user={user} />
            <PasswordSection token={token} />
            <TwoFASection user={user} token={token} onRefreshUser={refreshUser} />
          </Stack>
        ) : null}
      </PageLayout>
    </>
  );
}
