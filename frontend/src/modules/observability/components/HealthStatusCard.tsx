import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { HealthState } from "../types";

const statusColor: Record<HealthState, "success" | "warning" | "error" | "default"> = {
  healthy: "success",
  degraded: "warning",
  down: "error",
  unknown: "default",
};

export function titleCaseStatus(status: HealthState) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

type HealthStatusCardProps = {
  title: string;
  value: string;
  status: HealthState;
  caption?: string;
  loading?: boolean;
};

export default function HealthStatusCard({
  title,
  value,
  status,
  caption,
  loading,
}: HealthStatusCardProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        height: "100%",
        borderRadius: 2,
        borderColor: "divider",
        backgroundColor: "background.paper",
      }}
    >
      <Stack spacing={1.25}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Typography variant="body2" color="text.secondary">
            {title}
          </Typography>
          <Chip
            size="small"
            label={titleCaseStatus(status)}
            color={statusColor[status]}
            variant={status === "unknown" ? "outlined" : "filled"}
          />
        </Stack>
        {loading ? (
          <Skeleton variant="text" width="55%" height={34} />
        ) : (
          <Typography variant="h5" sx={{ fontWeight: 500 }}>
            {value}
          </Typography>
        )}
        {caption ? (
          <Typography variant="caption" color="text.secondary">
            {caption}
          </Typography>
        ) : null}
      </Stack>
    </Paper>
  );
}
