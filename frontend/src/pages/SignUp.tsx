import * as React from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormLabel from '@mui/material/FormLabel';
import Link from '@mui/material/Link';
import Checkbox from '@mui/material/Checkbox';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import AuthShell from '../components/auth/AuthShell';
import { setToken } from '../auth';

type SignUpFormState = {
  name: string;
  email: string;
  password: string;
  updatesOptIn: boolean;
};

const initialFormState: SignUpFormState = {
  name: '',
  email: '',
  password: '',
  updatesOptIn: true,
};

export default function SignUp(props: { disableCustomTheme?: boolean }) {
  const [form, setForm] = React.useState<SignUpFormState>(initialFormState);
  const [fieldErrors, setFieldErrors] = React.useState<{
    name?: string;
    email?: string;
    password?: string;
  }>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const navigate = useNavigate();

  const validate = React.useCallback(() => {
    const nextErrors: { name?: string; email?: string; password?: string } = {};

    if (!form.name.trim()) {
      nextErrors.name = 'Name is required.';
    }

    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) {
      nextErrors.email = 'Please enter a valid email address.';
    }

    if (!form.password || form.password.length < 8) {
      nextErrors.password = 'Password must be at least 8 characters long.';
    }

    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }, [form.email, form.name, form.password]);

  const handleChange =
    (field: keyof SignUpFormState) =>
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const value = field === 'updatesOptIn' ? event.target.checked : event.target.value;
      setForm((current) => ({ ...current, [field]: value }));
      setFormError(null);
      setFieldErrors((current) => ({ ...current, [field]: undefined }));
    };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validate()) {
      return;
    }

    setSubmitting(true);
    setFormError(null);

    try {
      const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: form.name.trim(),
          email: form.email.trim(),
          password: form.password,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setFormError(typeof err?.detail === 'string' ? err.detail : 'Sign up failed');
        return;
      }

      const json = await res.json();
      setToken(json.access_token);
      navigate('/dashboard', { replace: true });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Sign up failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      disableCustomTheme={props.disableCustomTheme}
      badge="Grower onboarding"
      badgeColor="warning"
      title="Request access without slowing down your field team."
      description="Create a grower profile. Access requests are reviewed by the agronomy operations team and validated against farm onboarding requirements."
      formTitle="Request onboarding"
      formSubtitle="Share the essentials so your workspace can be provisioned correctly the first time."
      aside={
        <Stack spacing={2.5}>
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Stack spacing={1.5}>
              <Typography variant="subtitle2">What to expect</Typography>
              <Grid container spacing={1.5}>
                {[
                  { value: '24h', label: 'Typical review window' },
                  { value: '3', label: 'Validation steps' },
                  { value: '1', label: 'Workspace handoff' },
                ].map((item) => (
                  <Grid key={item.label} size={{ xs: 12, sm: 4 }}>
                    <Typography variant="h5">{item.value}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {item.label}
                    </Typography>
                  </Grid>
                ))}
              </Grid>
            </Stack>
          </Paper>
          <Stack spacing={1.25}>
            {[
              'Farm ownership and operator identity verification.',
              'Device enrollment and control link review.',
              'Sensor calibration, imagery, and geofence setup.',
            ].map((item) => (
              <Paper key={item} variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" spacing={1.25} alignItems="center">
                  <Chip label="Review" size="small" color="warning" />
                  <Typography variant="body2" color="text.secondary">
                    {item}
                  </Typography>
                </Stack>
              </Paper>
            ))}
          </Stack>
        </Stack>
      }
      footer={
        <Typography sx={{ textAlign: 'center' }}>
          Already have an account?{' '}
          <Link component={RouterLink} to="/signin" variant="body2">
            Sign in
          </Link>
        </Typography>
      }
    >
      <Stack component="form" onSubmit={handleSubmit} spacing={2.25}>
        {formError ? <Alert severity="error">{formError}</Alert> : null}

        <FormControl>
          <FormLabel htmlFor="name">Full name</FormLabel>
          <TextField
            id="name"
            autoComplete="name"
            name="name"
            required
            fullWidth
            variant="filled"
            placeholder="Alex Morgan"
            value={form.name}
            onChange={handleChange('name')}
            error={Boolean(fieldErrors.name)}
            helperText={fieldErrors.name}
          />
        </FormControl>

        <FormControl>
          <FormLabel htmlFor="email">Email</FormLabel>
          <TextField
            required
            fullWidth
            id="email"
            placeholder="grower@farmco.com"
            name="email"
            autoComplete="email"
            variant="filled"
            value={form.email}
            onChange={handleChange('email')}
            error={Boolean(fieldErrors.email)}
            helperText={fieldErrors.email}
          />
        </FormControl>

        <FormControl>
          <FormLabel htmlFor="password">Password</FormLabel>
          <TextField
            required
            fullWidth
            name="password"
            placeholder="Create a secure password"
            type="password"
            id="password"
            autoComplete="new-password"
            variant="filled"
            value={form.password}
            onChange={handleChange('password')}
            error={Boolean(fieldErrors.password)}
            helperText={fieldErrors.password}
          />
        </FormControl>

        <FormControlLabel
          control={
            <Checkbox
              checked={form.updatesOptIn}
              onChange={handleChange('updatesOptIn')}
              color="primary"
            />
          }
          label="Notify me about platform updates"
        />

        <Button type="submit" fullWidth variant="contained" size="large" disabled={submitting}>
          {submitting ? 'Submitting request...' : 'Submit request'}
        </Button>
      </Stack>
    </AuthShell>
  );
}
