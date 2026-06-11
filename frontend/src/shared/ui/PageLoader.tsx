import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export type PageLoaderProps = {
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
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={title}
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
      <Stack
        spacing={3}
        sx={{ width: "100%", maxWidth: 480, textAlign: "center", alignItems: "center" }}
      >
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
          }}
        >
          Loading
        </Typography>
        <Typography variant="h3" sx={{ color: "text.primary", fontWeight: 500 }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
        <Box
          sx={{
            width: 120,
            height: 2,
            backgroundColor: "divider",
            position: "relative",
            overflow: "hidden",
            "&::after": {
              content: '""',
              position: "absolute",
              left: 0,
              top: 0,
              height: "100%",
              width: "40%",
              backgroundColor: "primary.main",
              animation: "loadingBar 1.5s cubic-bezier(0.5, 0, 0, 0.75) infinite",
              "@media (prefers-reduced-motion: reduce)": {
                animation: "none",
                left: "30%",
              },
            },
            "@keyframes loadingBar": {
              "0%": { left: "-40%" },
              "100%": { left: "100%" },
            },
          }}
        />
      </Stack>
    </Box>
  );
}
