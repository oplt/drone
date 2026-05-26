import { Box, Tooltip } from "@mui/material";
import type { RowStatus } from "../../preflight/preflightTypes";
import { statusDotColor } from "../../preflight/preflightUtils";

export function PreflightStatusDot({
  status,
  title,
}: {
  status: RowStatus;
  title: string;
}) {
  return (
    <Tooltip title={title}>
      <Box
        sx={{
          width: 12,
          height: 12,
          borderRadius: "50%",
          bgcolor: statusDotColor(status),
          border: "1px solid",
          borderColor: "rgba(0,0,0,0.18)",
          flexShrink: 0,
        }}
      />
    </Tooltip>
  );
}
