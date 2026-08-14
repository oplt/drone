import { Chip } from "@mui/material";

export function MissionTimelineStatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  const color =
    upper === "PASS" || upper === "completed"
      ? "success"
      : upper === "WARN"
        ? "warning"
        : "error";
  return <Chip label={upper} color={color as "success" | "warning" | "error"} size="small" sx={{ fontWeight: 600 }} />;
}
