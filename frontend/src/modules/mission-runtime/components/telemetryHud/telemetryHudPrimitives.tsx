import type { ReactNode } from "react";
import { Box, Typography } from "@mui/material";
import {
  TELEMETRY_HUD_GLASS,
  TELEMETRY_HUD_MONO,
  telemetryHudValueColor,
} from "./telemetryHudStyles";

export function HudMetric({
  label,
  value,
  warn,
  error,
}: {
  label: string;
  value: string;
  warn?: boolean;
  error?: boolean;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.15, minWidth: 0, flexShrink: 0 }}>
      <Typography
        component="span"
        sx={{
          fontSize: 8.5,
          fontWeight: 600,
          letterSpacing: 0.9,
          lineHeight: 1,
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.55)",
        }}
      >
        {label}
      </Typography>
      <Typography
        component="span"
        sx={{
          fontFamily: TELEMETRY_HUD_MONO,
          fontSize: 13,
          fontWeight: 700,
          lineHeight: 1.15,
          letterSpacing: 0.2,
          color: telemetryHudValueColor(warn, error),
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

export function HudDivider() {
  return (
    <Box
      sx={{
        width: "1px",
        alignSelf: "stretch",
        my: 0.25,
        bgcolor: "rgba(255,255,255,0.14)",
        flexShrink: 0,
      }}
    />
  );
}

export function GlassPanel({
  children,
  sx,
}: {
  children: ReactNode;
  sx?: Record<string, unknown>;
}) {
  return (
    <Box
      sx={{
        ...TELEMETRY_HUD_GLASS,
        px: 1.25,
        py: 0.75,
        display: "flex",
        alignItems: "center",
        gap: 1.25,
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}

export function DetailRow({
  label,
  value,
  warn,
  error,
}: {
  label: string;
  value: string;
  warn?: boolean;
  error?: boolean;
}) {
  return (
    <Box>
      <Typography
        component="div"
        sx={{
          fontSize: 8,
          fontWeight: 600,
          letterSpacing: 0.8,
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.45)",
          lineHeight: 1.1,
        }}
      >
        {label}
      </Typography>
      <Typography
        component="div"
        sx={{
          fontFamily: TELEMETRY_HUD_MONO,
          fontSize: 11,
          fontWeight: 600,
          color: telemetryHudValueColor(warn, error),
          lineHeight: 1.25,
          wordBreak: "break-word",
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}
