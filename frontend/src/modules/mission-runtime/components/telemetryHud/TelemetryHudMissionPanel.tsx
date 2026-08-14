import { Box, Typography } from "@mui/material";
import { GlassPanel } from "./telemetryHudPrimitives";
import { TELEMETRY_HUD_MONO } from "./telemetryHudStyles";
import type { TelemetryHudMissionPart } from "./telemetryHudTypes";

type TelemetryHudMissionPanelProps = {
  parts: TelemetryHudMissionPart[];
};

export function TelemetryHudMissionPanel({ parts }: TelemetryHudMissionPanelProps) {
  if (parts.length === 0) return null;

  return (
    <GlassPanel
      sx={{
        position: "absolute",
        bottom: 8,
        left: 8,
        maxWidth: "calc(58% - 12px)",
        flexDirection: "column",
        alignItems: "flex-start",
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
        Mission
      </Typography>
      <Typography
        sx={{
          fontFamily: TELEMETRY_HUD_MONO,
          fontSize: 11.5,
          fontWeight: 600,
          color: "common.white",
          lineHeight: 1.3,
          wordBreak: "break-word",
        }}
      >
        {parts.map((part, index) => (
          <Box component="span" key={part.text}>
            {index > 0 ? (
              <Box component="span" sx={{ color: "rgba(255,255,255,0.35)", mx: 0.6 }}>
                ·
              </Box>
            ) : null}
            <Box
              component="span"
              sx={{
                color: part.dim
                  ? "rgba(255,255,255,0.65)"
                  : part.emphasis
                    ? "common.white"
                    : "rgba(255,255,255,0.88)",
              }}
            >
              {part.text}
            </Box>
          </Box>
        ))}
      </Typography>
    </GlassPanel>
  );
}
