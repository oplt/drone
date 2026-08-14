import { Box, Typography } from "@mui/material";
import { GlassPanel } from "./telemetryHudPrimitives";
import { TELEMETRY_HUD_MONO } from "./telemetryHudStyles";
import type { DetectionHudInfo } from "./telemetryHudTypes";

type TelemetryHudDetectionPanelProps = {
  segments: string[];
  detection: DetectionHudInfo | undefined;
  detailsOpen: boolean;
};

export function TelemetryHudDetectionPanel({
  segments,
  detection,
  detailsOpen,
}: TelemetryHudDetectionPanelProps) {
  if (segments.length === 0) return null;

  return (
    <GlassPanel
      sx={{
        position: "absolute",
        bottom: 8,
        right: detailsOpen ? 148 : 44,
        maxWidth: "calc(58% - 12px)",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: 0.35,
        py: 0.65,
      }}
    >
      <Typography
        sx={{
          fontSize: 8.5,
          fontWeight: 600,
          letterSpacing: 0.9,
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.5)",
          lineHeight: 1,
        }}
      >
        Detection
      </Typography>
      <Typography
        sx={{
          fontFamily: TELEMETRY_HUD_MONO,
          fontSize: 11.5,
          fontWeight: 600,
          color: detection?.enabled ? "success.light" : "rgba(255,255,255,0.75)",
          lineHeight: 1.3,
          textAlign: "right",
        }}
      >
        {segments.map((segment, index) => (
          <Box component="span" key={segment}>
            {index > 0 ? (
              <Box component="span" sx={{ color: "rgba(255,255,255,0.35)", mx: 0.6 }}>
                ·
              </Box>
            ) : null}
            <Box component="span">{segment}</Box>
          </Box>
        ))}
      </Typography>
    </GlassPanel>
  );
}
