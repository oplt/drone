import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";

export function AccountLoadingSkeleton() {
  return (
    <Stack spacing={3}>
      <Skeleton variant="rounded" height={220} />
      <Skeleton variant="rounded" height={280} />
      <Skeleton variant="rounded" height={320} />
    </Stack>
  );
}
