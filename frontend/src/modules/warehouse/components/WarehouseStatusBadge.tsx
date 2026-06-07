import type { ReactNode } from "react";
import { Chip } from "@mui/material";

export type WarehouseUiStatus =
  | "ready"
  | "blocked"
  | "warning"
  | "waiting"
  | "running"
  | "deferred"
  | "unknown";

const STATUS_LABELS: Record<WarehouseUiStatus, string> = {
  ready: "Ready",
  blocked: "Blocked",
  warning: "Warning",
  waiting: "Waiting",
  running: "Running",
  deferred: "Deferred",
  unknown: "Unknown",
};

const STATUS_COLORS: Record<
  WarehouseUiStatus,
  "success" | "error" | "warning" | "info" | "default"
> = {
  ready: "success",
  blocked: "error",
  warning: "warning",
  waiting: "warning",
  running: "info",
  deferred: "info",
  unknown: "default",
};

export function WarehouseStatusBadge({
  status,
  children,
  size = "sm",
}: {
  status: WarehouseUiStatus;
  children?: ReactNode;
  size?: "sm" | "md";
}) {
  return (
    <Chip
      size={size === "sm" ? "small" : "medium"}
      color={STATUS_COLORS[status]}
      variant={
        status === "ready" || status === "blocked" ? "filled" : "outlined"
      }
      label={children ?? STATUS_LABELS[status]}
      sx={{
        fontWeight: 700,
        minHeight: size === "sm" ? 24 : 28,
        "& .MuiChip-label": { px: size === "sm" ? 0.9 : 1.1 },
      }}
    />
  );
}
