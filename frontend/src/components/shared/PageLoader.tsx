import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
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
      }}
    >
      <Stack spacing={2.5} sx={{ width: "100%", maxWidth: 1180 }}>
        <Paper
          variant="outlined"
          sx={(theme) => ({
            p: { xs: 3, md: 4 },
            borderRadius: 5,
            background:
              "linear-gradient(145deg, rgba(255,255,255,0.9), rgba(238,247,244,0.9))",
            ...theme.applyStyles("dark", {
              background:
                "linear-gradient(145deg, rgba(15,20,24,0.9), rgba(17,29,27,0.88))",
            }),
          })}
        >
          <Stack spacing={2}>
            <Stack spacing={1}>
              <Skeleton variant="rounded" width={140} height={22} />
              <Typography variant="h5">{title}</Typography>
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            </Stack>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <Skeleton variant="rounded" width={160} height={56} />
              <Skeleton variant="rounded" width={160} height={56} />
              <Skeleton variant="rounded" width={160} height={56} />
            </Stack>
          </Stack>
        </Paper>

        <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
          <Paper variant="outlined" sx={{ flex: 1, p: 3, borderRadius: 5 }}>
            <Stack spacing={2}>
              <Skeleton variant="rounded" width="38%" height={24} />
              <Skeleton variant="rounded" width="100%" height={220} />
              <Skeleton variant="rounded" width="72%" height={18} />
            </Stack>
          </Paper>
          <Paper variant="outlined" sx={{ width: { xs: "100%", lg: 320 }, p: 3, borderRadius: 5 }}>
            <Stack spacing={1.5}>
              <Skeleton variant="rounded" width="54%" height={24} />
              <Skeleton variant="rounded" width="100%" height={84} />
              <Skeleton variant="rounded" width="100%" height={84} />
              <Skeleton variant="rounded" width="100%" height={84} />
            </Stack>
          </Paper>
        </Stack>
      </Stack>
    </Box>
  );
}
