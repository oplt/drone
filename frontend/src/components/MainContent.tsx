import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import ShieldRoundedIcon from '@mui/icons-material/ShieldRounded';
import TrackChangesRoundedIcon from '@mui/icons-material/TrackChangesRounded';
import HubRoundedIcon from '@mui/icons-material/HubRounded';
import RadarRoundedIcon from '@mui/icons-material/RadarRounded';
import SatelliteAltRoundedIcon from '@mui/icons-material/SatelliteAltRounded';
import MemoryRoundedIcon from '@mui/icons-material/MemoryRounded';
import ArrowOutwardRoundedIcon from '@mui/icons-material/ArrowOutwardRounded';
import { Link as RouterLink } from 'react-router-dom';

const capabilities = [
  {
    title: 'Field flight planning',
    description:
      'Plan scouting, stand-count, and canopy passes with boundary-aware routing and automatic return paths.',
    icon: <TrackChangesRoundedIcon fontSize="small" />,
    meta: 'Fields + buffers + RTH',
  },
  {
    title: 'Crop health analytics',
    description:
      'NDVI, thermal, and RGB pipelines tuned for early stress detection and prescription-ready outputs.',
    icon: <ShieldRoundedIcon fontSize="small" />,
    meta: 'NDVI + thermal + RGB',
  },
  {
    title: 'Farm system integration',
    description:
      'Open APIs that connect to farm management systems, irrigation controllers, and field sensors.',
    icon: <HubRoundedIcon fontSize="small" />,
    meta: 'APIs + GIS + IoT',
  },
];

const liveStatuses = [
  { label: 'Field uplink', value: 'ACTIVE', icon: <SatelliteAltRoundedIcon /> },
  { label: 'Crop models', value: 'READY', icon: <RadarRoundedIcon /> },
  { label: 'Flight controller', value: 'ARMED', icon: <MemoryRoundedIcon /> },
];

const safeguards = [
  {
    title: 'Weather-aware autonomy',
    description: 'Wind, humidity, and temperature thresholds that pause flights and protect crops.',
  },
  {
    title: 'Reliable field comms',
    description: 'Graceful handoffs across rural networks with offline-safe route caching.',
  },
  {
    title: 'Traceable fieldwork',
    description: 'Audit-ready records for every flight, image set, and agronomy recommendation.',
  },
];

const statHighlights = [
  { value: '420k', label: 'Acres mapped' },
  { value: '18 min', label: 'Scout turnaround' },
  { value: '4.8x', label: 'Faster scouting' },
];

export default function MainContent() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: { xs: 7, md: 9 } }}>
      <Grid container spacing={{ xs: 3, md: 4 }} alignItems="stretch">
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper
            variant="outlined"
            sx={(theme) => ({
              height: '100%',
              px: { xs: 3, md: 5 },
              py: { xs: 3.5, md: 5 },
              background:
                'linear-gradient(145deg, rgba(255,255,255,0.9), rgba(242,249,246,0.88))',
              animation: 'riseIn 0.6s ease both',
              ...theme.applyStyles('dark', {
                background:
                  'linear-gradient(145deg, rgba(15,20,24,0.92), rgba(17,29,27,0.88))',
              }),
            })}
          >
            <Stack spacing={3.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} alignItems={{ sm: 'center' }}>
                <Chip label="Agronomy-ready autonomy" size="medium" color="success" />
                <Chip label="Field-secure" size="medium" variant="outlined" />
              </Stack>
              <Stack spacing={2}>
                <Typography variant="h1" sx={{ maxWidth: 760 }}>
                  Agronomy drone operations for healthier, higher-yield fields.
                </Typography>
                <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 620 }}>
                  A unified platform for scouting, telemetry, and imagery with agronomy-grade
                  safety controls. Built to operate across large acreage, remote blocks, and mixed
                  connectivity without slowing down field teams.
                </Typography>
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <Button
                  variant="contained"
                  size="large"
                  component={RouterLink}
                  to="/signup"
                  endIcon={<ArrowOutwardRoundedIcon fontSize="small" />}
                >
                  Request onboarding
                </Button>
                <Button variant="outlined" size="large" component={RouterLink} to="/signin">
                  Enter farm console
                </Button>
              </Stack>
              <Grid container spacing={1.5}>
                {statHighlights.map((item) => (
                  <Grid key={item.label} size={{ xs: 12, sm: 4 }}>
                    <Paper
                      variant="outlined"
                      sx={(theme) => ({
                        p: 2.25,
                        height: '100%',
                        backgroundColor: 'rgba(255,255,255,0.65)',
                        backdropFilter: 'blur(10px)',
                        ...theme.applyStyles('dark', {
                          backgroundColor: 'rgba(17,22,26,0.76)',
                        }),
                      })}
                    >
                      <Typography variant="h4">{item.value}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {item.label}
                      </Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </Stack>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Paper
            variant="outlined"
            sx={(theme) => ({
              p: { xs: 3, md: 4 },
              height: '100%',
              position: 'relative',
              overflow: 'hidden',
              background:
                'linear-gradient(150deg, hsla(174, 50%, 94%, 0.95), hsla(36, 60%, 97%, 0.9))',
              borderColor: 'hsla(174, 30%, 40%, 0.2)',
              animation: 'riseIn 0.8s ease both',
              ...theme.applyStyles('dark', {
                background:
                  'linear-gradient(150deg, hsla(172, 28%, 14%, 0.94), hsla(28, 24%, 13%, 0.9))',
              }),
            })}
          >
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                opacity: 0.42,
                backgroundImage:
                  'repeating-linear-gradient(0deg, transparent, transparent 18px, hsla(174, 20%, 40%, 0.15) 19px), repeating-linear-gradient(90deg, transparent, transparent 18px, hsla(174, 20%, 40%, 0.15) 19px)',
              }}
            />
            <Stack spacing={3} sx={{ position: 'relative', height: '100%' }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="overline" sx={{ color: 'text.secondary' }}>
                  Field ops snapshot
                </Typography>
                <Chip label="Field link" size="small" color="success" />
              </Stack>
              <Stack spacing={1.5}>
                {liveStatuses.map((item) => (
                  <Stack
                    key={item.label}
                    direction="row"
                    alignItems="center"
                    spacing={2}
                    sx={(theme) => ({
                      p: 2,
                      borderRadius: 3,
                      bgcolor: 'rgba(255,255,255,0.78)',
                      backdropFilter: 'blur(8px)',
                      border: '1px solid hsla(174, 30%, 40%, 0.16)',
                      ...theme.applyStyles('dark', {
                        bgcolor: 'rgba(17,22,26,0.78)',
                      }),
                    })}
                  >
                    <Box
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: 3,
                        display: 'grid',
                        placeItems: 'center',
                        bgcolor: 'hsla(174, 50%, 30%, 0.12)',
                      }}
                    >
                      {item.icon}
                    </Box>
                    <Box>
                      <Typography variant="subtitle2">{item.label}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {item.value}
                      </Typography>
                    </Box>
                  </Stack>
                ))}
              </Stack>
              <Divider />
              <Stack spacing={1}>
                <Typography variant="subtitle2">Why teams switch</Typography>
                <Typography variant="body2" color="text.secondary">
                  Operators see the route, telemetry, and live imagery in one place, which removes
                  the stop-start workflow between planning tools and field monitoring consoles.
                </Typography>
              </Stack>
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      <Box id="platform" sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Stack spacing={1}>
          <Typography variant="overline" sx={{ color: 'text.secondary' }}>
            Platform
          </Typography>
          <Typography variant="h2">Integrated scouting, telemetry, and imagery</Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 760 }}>
            Coordinate field flights across fleets with reliable telemetry and agronomy-grade
            imagery workflows. Every flight, image set, and report is traceable, export-ready,
            and easy for operators to act on quickly.
          </Typography>
        </Stack>
        <Grid container spacing={3}>
          {capabilities.map((capability, index) => (
            <Grid key={capability.title} size={{ xs: 12, md: 4 }}>
              <Paper
                variant="outlined"
                sx={{
                  p: 3,
                  height: '100%',
                  animation: 'riseIn 0.6s ease both',
                  animationDelay: `${index * 0.1}s`,
                }}
              >
                <Stack spacing={2}>
                  <Stack direction="row" spacing={1.25} alignItems="center">
                    <Box
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: 3,
                        display: 'grid',
                        placeItems: 'center',
                        bgcolor: 'hsla(174, 50%, 30%, 0.12)',
                      }}
                    >
                      {capability.icon}
                    </Box>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      {capability.meta}
                    </Typography>
                  </Stack>
                  <Typography variant="h6">{capability.title}</Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {capability.description}
                  </Typography>
                </Stack>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </Box>

      <Box id="safety" sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <Stack spacing={1}>
          <Typography variant="overline" sx={{ color: 'text.secondary' }}>
            Safety architecture
          </Typography>
          <Typography variant="h2">Controls that keep growers in command</Typography>
        </Stack>
        <Divider />
        <Grid container spacing={3}>
          {safeguards.map((item, index) => (
            <Grid key={item.title} size={{ xs: 12, md: 4 }}>
              <Paper
                variant="outlined"
                sx={{
                  p: 2.5,
                  height: '100%',
                  borderLeft: '3px solid hsla(174, 45%, 35%, 0.6)',
                  animation: 'riseIn 0.6s ease both',
                  animationDelay: `${index * 0.08}s`,
                }}
              >
                <Typography variant="h6" sx={{ mb: 1 }}>
                  {item.title}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {item.description}
                </Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </Box>

      <Box id="integration" sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Typography variant="overline" sx={{ color: 'text.secondary' }}>
          Integration
        </Typography>
        <Typography variant="h2">Drop into existing farm stacks</Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 760 }}>
          Compatible with GIS layers, weather feeds, and on-prem agronomy tools. Deployable as a
          single site or a distributed command mesh across farms and regions.
        </Typography>
      </Box>
    </Box>
  );
}
