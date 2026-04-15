import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

type PageLoaderProps = {
  fullScreen?: boolean;
  title?: string;
  subtitle?: string;
};

export default function PageLoader({
  fullScreen = false,
  title = "Loading workspace",
  subtitle = "Preparing live telemetry, charts, and controls.",
}: PageLoaderProps) {
  return (
    <Box
      sx={{
        minHeight: fullScreen ? "100dvh" : 420,
        width: "100%",
        px: { xs: 2, md: 4 },
        py: { xs: 3, md: 5 },
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "background.default",
      }}
    >
      <Stack spacing={3} sx={{ width: "100%", maxWidth: 480, textAlign: "center", alignItems: "center" }}>
        <Typography
          sx={{
            fontFamily: '"Space Mono", monospace',
            fontSize: '0.6875rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'text.secondary',
          }}
        >
          [LOADING...]
        </Typography>
        <Typography variant="h4" sx={{ color: 'text.primary' }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
        <Box
          sx={{
            width: 120,
            height: 2,
            backgroundColor: 'divider',
            position: 'relative',
            overflow: 'hidden',
            '&::after': {
              content: '""',
              position: 'absolute',
              left: 0,
              top: 0,
              height: '100%',
              width: '40%',
              backgroundColor: '#D71921',
              animation: 'loadingBar 1.5s cubic-bezier(0.25, 0.1, 0.25, 1) infinite',
            },
            '@keyframes loadingBar': {
              '0%': { left: '-40%' },
              '100%': { left: '100%' },
            },
          }}
        />
      </Stack>
    </Box>
  );
}
