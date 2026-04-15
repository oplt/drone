import * as React from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormLabel from '@mui/material/FormLabel';
import Grid from '@mui/material/Grid';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import ForgotPassword from '../components/ForgotPassword';
import AuthShell from '../components/auth/AuthShell';
import { setToken } from '../auth';

type SignInFormState = {
  email: string;
  password: string;
  rememberMe: boolean;
};

const initialFormState: SignInFormState = {
  email: '',
  password: '',
  rememberMe: false,
};

export default function SignIn(props: { disableCustomTheme?: boolean }) {
  const [form, setForm] = React.useState<SignInFormState>(initialFormState);
  const [fieldErrors, setFieldErrors] = React.useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  const navigate = useNavigate();

  React.useEffect(() => {
    const rememberedEmail = localStorage.getItem('remembered_email');
    if (rememberedEmail) {
      setForm((current) => ({
        ...current,
        email: rememberedEmail,
        rememberMe: true,
      }));
    }
  }, []);

  const validate = React.useCallback(() => {
    const nextErrors: { email?: string; password?: string } = {};

    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) {
      nextErrors.email = 'Please enter a valid email address.';
    }

    if (!form.password) {
      nextErrors.password = 'Password is required.';
    }

    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }, [form.email, form.password]);

  const handleChange =
    (field: keyof SignInFormState) =>
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const value = field === 'rememberMe' ? event.target.checked : event.target.value;
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
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email.trim(),
          password: form.password,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const message = typeof err?.detail === 'string' ? err.detail : 'Login failed';
        setFormError(message);
        return;
      }

      const json = await res.json();
      setToken(json.access_token);

      if (form.rememberMe) {
        localStorage.setItem('remembered_email', form.email.trim());
      } else {
        localStorage.removeItem('remembered_email');
      }

      navigate('/dashboard', { replace: true });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      disableCustomTheme={props.disableCustomTheme}
      badge="Field console"
      badgeColor="success"
      title="Grower access with the right information first."
      description="Sign in to plan field flights, review imagery, and monitor telemetry across your farms. Access is restricted to authorized agronomy teams."
      formTitle="Sign in"
      formSubtitle="Use your operator credentials to open the live command console."
      aside={
        <Stack spacing={2.5}>
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Stack spacing={1.5}>
              <Typography variant="subtitle2">Live field summary</Typography>
              <Grid container spacing={1.5}>
                {[
                  { value: '99.2%', label: 'Uplink health' },
                  { value: '12', label: 'Ready flights' },
                  { value: '3 min', label: 'Imagery sync delay' },
                ].map((item) => (
                  <Grid key={item.label} size={{ xs: 12, sm: 4 }}>
                    <Box>
                      <Typography variant="h5">{item.value}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {item.label}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Stack>
          </Paper>
          <Stack spacing={1.25}>
            {[
              'All systems nominal. Flight queue synchronized.',
              'Telemetry link active and operator alerts routed.',
              'Field plans and imagery sync automatically after sign-in.',
            ].map((item) => (
              <Paper key={item} variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" spacing={1.25} alignItems="center">
                  <Chip label="Live" size="small" color="success" />
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
          Don&apos;t have an account?{' '}
          <Link component={RouterLink} to="/signup" variant="body2">
            Request onboarding
          </Link>
        </Typography>
      }
    >
      <Stack
        component="form"
        onSubmit={handleSubmit}
        noValidate
        spacing={2.25}
      >
        {formError ? <Alert severity="error">{formError}</Alert> : null}

        <FormControl>
          <FormLabel htmlFor="email">Email</FormLabel>
          <TextField
            id="email"
            type="email"
            name="email"
            placeholder="grower@farmco.com"
            autoComplete="email"
            autoFocus
            required
            fullWidth
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
            id="password"
            name="password"
            placeholder="Enter your password"
            type="password"
            autoComplete="current-password"
            required
            fullWidth
            variant="filled"
            value={form.password}
            onChange={handleChange('password')}
            error={Boolean(fieldErrors.password)}
            helperText={fieldErrors.password}
          />
        </FormControl>

        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
          <FormControlLabel
            control={
              <Checkbox
                checked={form.rememberMe}
                onChange={handleChange('rememberMe')}
                color="primary"
              />
            }
            label="Remember this device"
          />
          <Link
            component="button"
            type="button"
            onClick={() => setOpen(true)}
            variant="body2"
            sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}
          >
            Forgot your password?
          </Link>
        </Stack>

        <Button type="submit" fullWidth variant="contained" size="large" disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </Button>
      </Stack>

      <ForgotPassword open={open} handleClose={() => setOpen(false)} />
    </AuthShell>
  );
}
