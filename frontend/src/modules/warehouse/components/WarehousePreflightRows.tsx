import { Box, Stack, Typography } from "@mui/material";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
import HourglassEmptyRoundedIcon from "@mui/icons-material/HourglassEmptyRounded";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  WarehouseStatusBadge,
  type WarehouseUiStatus,
} from "./WarehouseStatusBadge";
import type { PreflightCheckView } from "./warehousePreflightViewModel";

const ICON_COLOR: Record<
  WarehouseUiStatus,
  "success" | "error" | "warning" | "info" | "disabled"
> = {
  ready: "success",
  blocked: "error",
  warning: "warning",
  waiting: "warning",
  running: "info",
  deferred: "info",
  unknown: "disabled",
};

function CheckIcon({ status }: { status: WarehouseUiStatus }) {
  const color = ICON_COLOR[status];
  if (status === "ready") {
    return <CheckCircleOutlineRoundedIcon fontSize="small" color={color} />;
  }
  if (status === "blocked") {
    return <ErrorOutlineRoundedIcon fontSize="small" color={color} />;
  }
  if (status === "deferred") {
    return <InfoOutlinedIcon fontSize="small" color={color} />;
  }
  return <HourglassEmptyRoundedIcon fontSize="small" color={color} />;
}

function PreflightCheckRow({ check }: { check: PreflightCheckView }) {
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      sx={{
        py: 0.75,
        minWidth: 0,
        borderTop: "1px solid",
        borderColor: "divider",
      }}
    >
      <CheckIcon status={check.status} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 650, lineHeight: 1.25 }}>
          {check.label}
        </Typography>
        {check.detail ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ wordBreak: "break-word" }}
          >
            {check.detail}
          </Typography>
        ) : null}
      </Box>
      <WarehouseStatusBadge status={check.status}>
        {check.rawStatus}
      </WarehouseStatusBadge>
    </Stack>
  );
}

export function PreflightGroup({
  title,
  checks,
}: {
  title: string;
  checks: PreflightCheckView[];
}) {
  const passed = checks.filter((check) => check.status === "ready").length;
  return (
    <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: "action.hover" }}>
      <Stack spacing={0.5}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          spacing={1}
        >
          <Typography variant="body2" sx={{ fontWeight: 750 }}>
            {title}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontFamily: "monospace" }}
          >
            {passed}/{checks.length}
          </Typography>
        </Stack>
        {checks.map((check) => (
          <PreflightCheckRow key={check.key} check={check} />
        ))}
      </Stack>
    </Box>
  );
}
