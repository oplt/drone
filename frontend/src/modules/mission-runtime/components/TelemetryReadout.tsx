import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";

const MONO = '"Roboto Mono", "SFMono-Regular", Consolas, monospace';

export type TelemetryReadoutProps = {
  label: string;
  value: string;
  tooltip?: string;
  /** Compact panel tone (dashboard/fleet). HUD glass uses glass variant. */
  variant?: "panel" | "glass";
  warn?: boolean;
  error?: boolean;
  sx?: SxProps<Theme>;
};

function valueColor(warn?: boolean, error?: boolean, glass?: boolean) {
  if (error) return glass ? "error.light" : "error.main";
  if (warn) return glass ? "warning.light" : "warning.main";
  return glass ? "common.white" : "text.primary";
}

/** Shared telemetry metric readout (HUD-inspired mono + warn/error). */
export function TelemetryReadout({
  label,
  value,
  tooltip,
  variant = "panel",
  warn,
  error,
  sx,
}: TelemetryReadoutProps) {
  const glass = variant === "glass";
  const body = (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.15, minWidth: 0, ...((sx as object) ?? {}) }}>
      <Typography
        component="span"
        sx={{
          fontSize: glass ? 8.5 : 11,
          fontWeight: 600,
          letterSpacing: glass ? 0.9 : 0.4,
          lineHeight: 1,
          textTransform: "uppercase",
          color: glass ? "rgba(255,255,255,0.55)" : "text.secondary",
        }}
      >
        {label}
      </Typography>
      <Typography
        component="span"
        sx={{
          fontFamily: MONO,
          fontSize: glass ? 13 : 16,
          fontWeight: 700,
          lineHeight: 1.15,
          letterSpacing: 0.2,
          color: valueColor(warn, error, glass),
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </Typography>
    </Box>
  );

  if (tooltip) {
    return (
      <Tooltip title={tooltip} arrow>
        {body}
      </Tooltip>
    );
  }
  return body;
}

export function TelemetryReadoutRow({
  children,
  sx,
}: {
  children: React.ReactNode;
  sx?: SxProps<Theme>;
}) {
  return (
    <Stack
      direction="row"
      spacing={2}
      useFlexGap
      flexWrap="wrap"
      alignItems="flex-start"
      sx={sx}
    >
      {children}
    </Stack>
  );
}
