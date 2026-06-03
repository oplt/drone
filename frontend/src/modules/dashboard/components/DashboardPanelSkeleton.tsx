import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";

export default function DashboardPanelSkeleton({
  height = 280,
}: {
  height?: number;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 3, borderRadius: 4, minHeight: height }}>
      <Stack spacing={2}>
        <Skeleton variant="rounded" width="36%" height={24} />
        <Skeleton variant="rounded" width="100%" height={height - 60} />
      </Stack>
    </Paper>
  );
}
