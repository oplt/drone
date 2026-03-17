import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Link from '@mui/material/Link';
import SitemarkIcon from './SitemarkIcon';
import { Link as RouterLink } from 'react-router-dom';

function Copyright() {
  return (
    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
      Copyright © TerraField Agronomy {new Date().getFullYear()}
    </Typography>
  );
}

export default function Footer() {
  return (
    <Box id="contact" sx={{ mt: { xs: 8, md: 10 } }}>
      <Divider />
      <Container
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: { xs: 4, sm: 5 },
          py: { xs: 6, sm: 8 },
        }}
      >
        <Stack
          direction={{ xs: 'column', lg: 'row' }}
          spacing={4}
          sx={{ justifyContent: 'space-between' }}
        >
          <Stack spacing={2} sx={{ maxWidth: 440 }}>
            <SitemarkIcon />
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Aerial agronomy operations for crop scouting, stand counts, and irrigation planning.
              Built for traceable fieldwork, resilient connectivity, and agronomic collaboration.
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              ops@terrafield.ag
            </Typography>
          </Stack>
          <Stack spacing={1.5}>
            <Typography variant="subtitle2">Access</Typography>
            <Link component={RouterLink} to="/signin" color="text.secondary">
              Grower sign-in
            </Link>
            <Link component={RouterLink} to="/signup" color="text.secondary">
              Request onboarding
            </Link>
            <Link href="#platform" color="text.secondary">
              Platform overview
            </Link>
          </Stack>
          <Stack spacing={1.5}>
            <Typography variant="subtitle2">Data & Privacy</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Field-level access controls
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Exportable agronomy reports
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Regional data residency options
            </Typography>
          </Stack>
        </Stack>
        <Divider />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
          <Copyright />
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            All features shown are configurable and subject to agronomy program needs.
          </Typography>
        </Stack>
      </Container>
    </Box>
  );
}
