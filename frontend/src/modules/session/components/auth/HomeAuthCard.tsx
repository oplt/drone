import * as React from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Checkbox from '@mui/material/Checkbox';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormLabel from '@mui/material/FormLabel';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LoginIcon from '@mui/icons-material/Login';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import { alpha } from '@mui/material/styles';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { sessionKeys } from '../../../../app/config/queryKeys';
import ForgotPassword from '../ForgotPassword';
import { ApiError } from "../../../../shared/api/apiError";
import { login, setToken, signUp } from '../../';
import { ActionIconButton } from '../../../../shared/ui/ActionIconButton';

export type AuthMode = 'signIn' | 'signUp';

type HomeAuthCardProps = {
  initialMode?: AuthMode;
};

type SignInFormState = {
  email: string;
  password: string;
  rememberMe: boolean;
};

type SignUpFormState = {
  name: string;
  email: string;
  password: string;
  updatesOptIn: boolean;
};

const initialSignInState: SignInFormState = {
  email: '',
  password: '',
  rememberMe: false,
};

const initialSignUpState: SignUpFormState = {
  name: '',
  email: '',
  password: '',
  updatesOptIn: true,
};

function ToggleButton({
  active,
  title,
  icon,
  onClick,
}: {
  active: boolean;
  title: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <Tooltip title={title}>
      <span>
        <IconButton
          type="button"
          aria-pressed={active}
          aria-label={title}
          onClick={onClick}
          color={active ? 'primary' : 'default'}
          sx={{ minHeight: 40, borderRadius: 999, width: '100%' }}
        >
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  );
}

function SignInForm() {
  const [form, setForm] = React.useState<SignInFormState>(initialSignInState);
  const [fieldErrors, setFieldErrors] = React.useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [forgotOpen, setForgotOpen] = React.useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

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
    if (!validate()) return;

    setSubmitting(true);
    setFormError(null);

    try {
      const json = await login({
        email: form.email.trim(),
        password: form.password,
        remember_me: form.rememberMe,
      });

      if (json.access_token) {
        setToken(json.access_token);
      }

      if (form.rememberMe) {
        localStorage.setItem('remembered_email', form.email.trim());
      } else {
        localStorage.removeItem('remembered_email');
      }

      await queryClient.invalidateQueries({ queryKey: sessionKeys.verified() });
      navigate('/dashboard', { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        setFormError(error.detail ?? error.message);
      } else {
        setFormError(error instanceof Error ? error.message : 'Login failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Stack component="form" onSubmit={handleSubmit} noValidate spacing={2}>
      {formError ? <Alert severity="error">{formError}</Alert> : null}

      <FormControl>
        <FormLabel htmlFor="home-signin-email">Email</FormLabel>
        <TextField
          id="home-signin-email"
          type="email"
          name="email"
          placeholder="grower@farmco.com"
          autoComplete="email"
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
        <FormLabel htmlFor="home-signin-password">Password</FormLabel>
        <TextField
          id="home-signin-password"
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
          onClick={() => setForgotOpen(true)}
          variant="body2"
          sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}
        >
          Forgot your password?
        </Link>
      </Stack>

      <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
        <ActionIconButton
          type="submit"
          variant="check"
          title={submitting ? 'Signing in…' : 'Sign in'}
          color="primary"
          size="large"
          loading={submitting}
          disabled={submitting}
        />
      </Box>
      <ForgotPassword open={forgotOpen} handleClose={() => setForgotOpen(false)} />
    </Stack>
  );
}

function SignUpForm() {
  const [form, setForm] = React.useState<SignUpFormState>(initialSignUpState);
  const [fieldErrors, setFieldErrors] = React.useState<{
    name?: string;
    email?: string;
    password?: string;
  }>({});
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

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
    if (!validate()) return;

    setSubmitting(true);
    setFormError(null);

    try {
      const json = await signUp({
        full_name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
      });
      if (json.access_token) {
        setToken(json.access_token);
      }
      await queryClient.invalidateQueries({ queryKey: sessionKeys.verified() });
      navigate('/dashboard', { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        setFormError(error.detail ?? error.message);
      } else {
        setFormError(error instanceof Error ? error.message : 'Sign up failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Stack component="form" onSubmit={handleSubmit} noValidate spacing={2}>
      {formError ? <Alert severity="error">{formError}</Alert> : null}

      <FormControl>
        <FormLabel htmlFor="home-signup-name">Full name</FormLabel>
        <TextField
          id="home-signup-name"
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
        <FormLabel htmlFor="home-signup-email">Email</FormLabel>
        <TextField
          required
          fullWidth
          id="home-signup-email"
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
        <FormLabel htmlFor="home-signup-password">Password</FormLabel>
        <TextField
          required
          fullWidth
          name="password"
          placeholder="Create a secure password"
          type="password"
          id="home-signup-password"
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

      <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
        <ActionIconButton
          type="submit"
          variant="check"
          title={submitting ? 'Submitting request…' : 'Submit request'}
          color="primary"
          size="large"
          loading={submitting}
          disabled={submitting}
        />
      </Box>
    </Stack>
  );
}

function AuthFace({
  active,
  flipped,
  children,
}: {
  active: boolean;
  flipped?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Box
      aria-hidden={!active}
      sx={{
        position: flipped ? 'absolute' : 'relative',
        inset: flipped ? 0 : 'auto',
        backfaceVisibility: 'hidden',
        transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
        visibility: active ? 'visible' : 'hidden',
        pointerEvents: active ? 'auto' : 'none',
      }}
    >
      {children}
    </Box>
  );
}

export default function HomeAuthCard({ initialMode = 'signIn' }: HomeAuthCardProps) {
  const [mode, setMode] = React.useState<AuthMode>(initialMode);

  React.useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  const isSignIn = mode === 'signIn';

  return (
    <Paper
      variant="outlined"
      sx={(theme) => ({
        width: '100%',
        maxWidth: { xs: 'none', lg: 550 },
        ml: { lg: 'auto' },
        p: { xs: 2.25, sm: 3.75 },
        borderRadius: 2,
        overflow: 'hidden',
        backgroundColor: alpha(theme.palette.background.paper, 0.9),
        backdropFilter: 'blur(16px)',
        boxShadow: `0 22px 70px ${alpha(theme.palette.common.black, 0.12)}`,
      })}
    >
      <Stack spacing={4}>
        <Stack spacing={3}>
          <Typography variant="overline" color="text.secondary">
            Drone ops access
          </Typography>
          <Typography component="h2" variant="h5">
            {isSignIn ? 'Enter farm console' : 'Request onboarding'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isSignIn
              ? 'Use your operator credentials to open the live command console.'
              : 'Share the essentials so your workspace can be provisioned correctly.'}
          </Typography>
        </Stack>

        <Box
          sx={(theme) => ({
            p: 0.5,
            display: 'grid',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: 0.75,
            borderRadius: 999,
            backgroundColor: alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.12 : 0.06),
          })}
        >
          <ToggleButton
            active={isSignIn}
            title="Sign in"
            icon={<LoginIcon fontSize="small" />}
            onClick={() => setMode('signIn')}
          />
          <ToggleButton
            active={!isSignIn}
            title="Sign up"
            icon={<PersonAddIcon fontSize="small" />}
            onClick={() => setMode('signUp')}
          />
        </Box>

        <Box sx={{ perspective: 1400 }}>
          <Box
            sx={{
              position: 'relative',
              minHeight: { xs: isSignIn ? 390 : 520, sm: isSignIn ? 360 : 500 },
              transformStyle: 'preserve-3d',
              transform: isSignIn ? 'rotateY(0deg)' : 'rotateY(180deg)',
              transition: 'transform 520ms cubic-bezier(0.2, 0.8, 0.2, 1), min-height 240ms ease',
              '@media (prefers-reduced-motion: reduce)': {
                transition: 'none',
              },
            }}
          >
            <AuthFace active={isSignIn}>
              <SignInForm />
            </AuthFace>
            <AuthFace active={!isSignIn} flipped>
              <SignUpForm />
            </AuthFace>
          </Box>
        </Box>
      </Stack>
    </Paper>
  );
}
