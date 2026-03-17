import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getToken } from '../../../auth';
import { apiRequest } from '../../../utils/api';
import InfoLabel from '../../../components/dashboard/InfoLabel';
import Header from '../../../components/dashboard/Header';
import PageLayout, { PageSection } from '../../../components/dashboard/PageLayout';

type UserResponse = {
  id: string;
  email: string;
  full_name: string | null;
  created_at?: string;
};

type UserUpdate = {
  full_name?: string;
};

function initials(name: string | null | undefined): string {
  if (!name) return '?';
  return name
    .trim()
    .split(/\s+/)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .slice(0, 2)
    .join('');
}

function ProfileSkeleton() {
  return (
    <Stack spacing={3}>
      <Skeleton variant="rounded" height={220} />
      <Skeleton variant="rounded" height={260} />
    </Stack>
  );
}

export default function ProfilePage() {
  const token = getToken();
  const queryClient = useQueryClient();

  const { data: user, isLoading: userLoading, error: userError } = useQuery<UserResponse>({
    queryKey: ['me'],
    enabled: Boolean(token),
    queryFn: () => apiRequest<UserResponse>('/auth/me', {}, token),
  });

  const [fullName, setFullName] = useState('');

  useEffect(() => {
    if (user) {
      setFullName(user.full_name ?? '');
    }
  }, [user]);

  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const userMutation = useMutation({
    mutationFn: (payload: UserUpdate) =>
      apiRequest('/auth/me', { method: 'PATCH', body: JSON.stringify(payload) }, token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['me'] });
      setSaveSuccess(true);
      setSaveError(null);
    },
    onError: (error: unknown) => {
      setSaveError(error instanceof Error ? error.message : 'Failed to save profile.');
      setSaveSuccess(false);
    },
  });

  const handleSaveBasic = () => {
    setSaveSuccess(false);
    setSaveError(null);
    userMutation.mutate({
      full_name: fullName.trim(),
    });
  };

  return (
    <>
      <Header />
      <PageLayout
        eyebrow="Profile"
        title={user?.full_name || 'Your profile'}
        description="Keep your operator identity and profile details current so access, alerts, and activity logs stay accurate."
        metrics={[
          {
            label: 'Email',
            value: user?.email ?? '--',
            caption: 'Primary operator address',
          },
          {
            label: 'Member since',
            value:
              user?.created_at != null
                ? new Date(user.created_at).toLocaleDateString()
                : '--',
            caption: 'Account creation date',
          },
          {
            label: 'Profile status',
            value: user ? 'Active' : '--',
            caption: 'Ready for field operations',
          },
        ]}
        hero={
          <PageSection sx={{ height: '100%', p: 2.5 }}>
            <Stack direction="row" spacing={2} alignItems="center">
              <Avatar
                sx={{
                  width: 68,
                  height: 68,
                  bgcolor: 'primary.main',
                  fontSize: 24,
                  fontWeight: 700,
                }}
              >
                {initials(user?.full_name)}
              </Avatar>
              <Box>
                <Typography variant="h5">{user?.full_name || 'Operator profile'}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {user?.email ?? 'No email available'}
                </Typography>
              </Box>
            </Stack>
          </PageSection>
        }
      >
        {userLoading ? <ProfileSkeleton /> : null}
        {userError || !user ? (
          <Alert severity="error">Failed to load profile. Please refresh the page.</Alert>
        ) : null}

        {!userLoading && user ? (
          <PageSection title="Personal information" description="Update your public operator details used across the dashboard.">
            <Stack spacing={2.5}>
              {saveSuccess ? (
                <Alert severity="success" onClose={() => setSaveSuccess(false)}>
                  Profile updated successfully.
                </Alert>
              ) : null}
              {saveError ? (
                <Alert severity="error" onClose={() => setSaveError(null)}>
                  {saveError}
                </Alert>
              ) : null}

              <TextField
                fullWidth
                label="Full name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                slotProps={{ htmlInput: { maxLength: 200 } }}
                variant="filled"
              />

              <TextField
                fullWidth
                label={
                  <InfoLabel
                    label="Email"
                    info="Email cannot be changed here. Contact support if you need to update it."
                  />
                }
                InputLabelProps={{ shrink: true, sx: { pointerEvents: 'auto' } }}
                value={user.email ?? ''}
                disabled
                variant="filled"
              />

              <Box>
                <Button
                  variant="contained"
                  onClick={handleSaveBasic}
                  disabled={userMutation.isPending || !fullName.trim()}
                >
                  {userMutation.isPending ? 'Saving...' : 'Save changes'}
                </Button>
              </Box>
            </Stack>
          </PageSection>
        ) : null}
      </PageLayout>
    </>
  );
}
