import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import {
  useTelemetryLinkStatus,
  type TelemetryLinkStatus,
} from "../../modules/mission-runtime/hooks/useTelemetryLinkStatus";

type TelemetryLinkChipProps = {
  size?: "small" | "medium";
  /** Compact mobile label */
  compact?: boolean;
  enabled?: boolean;
};

function compactLabel(status: TelemetryLinkStatus): string {
  if (status.phase === "live") return "Live";
  if (status.phase === "stale") return "Stale";
  if (status.phase === "reconnecting") return "Reconnect";
  return "Offline";
}

export default function TelemetryLinkChip({
  size = "small",
  compact = false,
  enabled = true,
}: TelemetryLinkChipProps) {
  const status = useTelemetryLinkStatus({ enabled });
  const label = compact ? compactLabel(status) : status.label;
  const title =
    status.ageSec != null
      ? `${status.label}. Last packet ${status.ageSec}s ago.`
      : status.label;

  return (
    <Tooltip title={title} arrow>
      <Chip
        size={size}
        color={status.color}
        label={label}
        variant={status.phase === "live" ? "filled" : "outlined"}
        aria-label={status.label}
      />
    </Tooltip>
  );
}
