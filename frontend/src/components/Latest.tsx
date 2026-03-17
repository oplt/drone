import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import FlightRoundedIcon from '@mui/icons-material/FlightRounded';
import VideocamRoundedIcon from '@mui/icons-material/VideocamRounded';
import SensorsRoundedIcon from '@mui/icons-material/SensorsRounded';

const readiness = [
  {
    title: 'Field scouting workflow',
    description: 'Validated preflight routes with boundary-aware reroutes and safe return paths.',
    icon: <FlightRoundedIcon />,
  },
  {
    title: 'Sensor data quality',
    description: 'Consistent NDVI/RGB calibration with automated anomaly detection and alerts.',
    icon: <SensorsRoundedIcon />,
  },
  {
    title: 'Imagery delivery',
    description: 'Adaptive streaming with export-ready metadata for agronomy reporting.',
    icon: <VideocamRoundedIcon />,
  },
];

const checklist = [
  'Load field boundaries and crop zones.',
  'Verify wind, humidity, and spray window thresholds.',
  'Calibrate sensors and reflectance targets.',
  'Confirm return-to-home and battery reserve limits.',
  'Run a dry flight and export a sample report.',
];

export default function Latest() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <Stack spacing={1.25}>
        <Typography variant="overline" sx={{ color: 'text.secondary' }}>
          Field readiness
        </Typography>
        <Typography variant="h2">Grower-ready building blocks</Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 760 }}>
          Designed for agronomy teams that need consistent telemetry, reliable imagery, and
          configurable autonomy with human-in-the-loop controls.
        </Typography>
      </Stack>
      <Grid container spacing={3}>
        {readiness.map((item, index) => (
          <Grid key={item.title} size={{ xs: 12, md: 4 }}>
            <Paper
              variant="outlined"
              sx={{
                p: 3,
                height: '100%',
                animation: 'riseIn 0.6s ease both',
                animationDelay: `${index * 0.12}s`,
              }}
            >
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
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
                  <Chip label="Ready" size="small" color="success" />
                </Stack>
                <Typography variant="h6">{item.title}</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {item.description}
                </Typography>
              </Stack>
            </Paper>
          </Grid>
        ))}
      </Grid>

      <Paper variant="outlined" sx={{ p: { xs: 3, md: 4 } }}>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 4 }}>
            <Stack spacing={1.5}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <CheckCircleRoundedIcon color="success" />
                <Typography variant="h6">Launch checklist</Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                Every onboarding includes a dry-run checklist so teams can validate operations
                before moving into live acreage.
              </Typography>
            </Stack>
          </Grid>
          <Grid size={{ xs: 12, md: 8 }}>
            <Divider sx={{ display: { xs: 'block', md: 'none' }, mb: 2 }} />
            <Stack spacing={1.5}>
              {checklist.map((item) => (
                <Paper
                  key={item}
                  variant="outlined"
                  sx={(theme) => ({
                    p: 2,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1.5,
                    backgroundColor: 'rgba(255,255,255,0.72)',
                    ...theme.applyStyles('dark', {
                      backgroundColor: 'rgba(17,22,26,0.72)',
                    }),
                  })}
                >
                  <CheckCircleRoundedIcon color="success" fontSize="small" />
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {item}
                  </Typography>
                </Paper>
              ))}
            </Stack>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  );
}
