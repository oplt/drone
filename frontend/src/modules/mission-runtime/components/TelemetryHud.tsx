import * as React from "react";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { Box, Collapse, IconButton, Stack, Typography } from "@mui/material";
import { deriveTelemetry } from "../utils/deriveTelemetry";

const MONO = '"Roboto Mono", "SFMono-Regular", Consolas, monospace';

const GLASS = {
  bgcolor: "rgba(0, 0, 0, 0.38)",
  backdropFilter: "blur(10px)",
  WebkitBackdropFilter: "blur(10px)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  borderRadius: 2,
  boxShadow: "0 2px 12px rgba(0, 0, 0, 0.25)",
} as const;

function valueColor(warn?: boolean, error?: boolean) {
  if (error) return "error.light";
  if (warn) return "warning.light";
  return "common.white";
}

function HudMetric({
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
          fontFamily: MONO,
          fontSize: 13,
          fontWeight: 700,
          lineHeight: 1.15,
          letterSpacing: 0.2,
          color: valueColor(warn, error),
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

function HudDivider() {
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

function GlassPanel({
  children,
  sx,
}: {
  children: React.ReactNode;
  sx?: Record<string, unknown>;
}) {
  return (
    <Box
      sx={{
        ...GLASS,
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

export type DetectionHudInfo = {
  enabled: boolean;
  modelName?: string | null;
  fps?: number | null;
  framesProcessed?: number;
  lastError?: string | null;
};

export type TelemetryHudProps = {
  telemetry: unknown;
  cameraTitle?: string;
  missionLabel?: string | null;
  recordingStatus?: string | null;
  detection?: DetectionHudInfo;
  sx?: Record<string, unknown>;
};

function formatModelName(path?: string | null): string | null {
  if (!path) return null;
  const base = path.split("/").pop()?.replace(/\.pt$/i, "") ?? path;
  return base.replace(/[-_]/g, "").toUpperCase();
}

export function TelemetryHud({
  telemetry,
  cameraTitle = "Survey Camera",
  missionLabel,
  recordingStatus,
  detection,
  sx,
}: TelemetryHudProps) {
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const d = React.useMemo(() => deriveTelemetry(telemetry), [telemetry]);

  const batteryPct = React.useMemo(() => {
    const match = d.batteryShort.match(/(\d+)/);
    return match ? Number.parseInt(match[1], 10) : null;
  }, [d.batteryShort]);

  const batteryWarn = batteryPct !== null && batteryPct < 30;
  const batteryError = batteryPct !== null && batteryPct < 15;
  const gpsWarn = d.gpsShort === "GPS NO FIX" || d.gpsShort === "GPS 2D";
  const gpsError = d.gpsShort === "GPS NO FIX";
  const statusError = d.statusShort === "EMERGENCY" || d.statusShort === "RTL";
  const failsafeError = d.failsafeShort !== "SAFE";

  const bottomLeftParts = [
    { text: cameraTitle, emphasis: true },
    missionLabel ? { text: missionLabel } : null,
    recordingStatus ? { text: recordingStatus, dim: true } : null,
  ].filter(Boolean) as Array<{ text: string; emphasis?: boolean; dim?: boolean }>;

  const modelShort = formatModelName(detection?.modelName);
  const detectionSegments = [
    modelShort,
    detection?.fps != null ? `${detection.fps} FPS` : null,
    detection?.enabled ? "ON" : detection ? "OFF" : null,
  ].filter(Boolean) as string[];

  return (
    <Box
      sx={{
        position: "absolute",
        inset: 0,
        zIndex: 2,
        pointerEvents: "none",
        ...sx,
      }}
    >
      <GlassPanel
        sx={{
          position: "absolute",
          top: 8,
          left: 8,
          right: detailsOpen ? 148 : 44,
          maxWidth: "calc(100% - 16px)",
          flexWrap: "wrap",
          rowGap: 0.5,
        }}
      >
        <HudMetric label="Status" value={d.statusShort} error={statusError} warn={d.statusShort === "ARMED"} />
        <HudDivider />
        <HudMetric label="Mode" value={d.modeShort} />
        <HudDivider />
        <HudMetric label="Speed" value={d.speedShort} />
        <HudDivider />
        <HudMetric label="Alt" value={d.altShort} />
        <HudDivider />
        <HudMetric label="GPS" value={d.gpsShort} warn={gpsWarn} error={gpsError} />
        <HudDivider />
        <HudMetric label="Battery" value={d.batteryShort} warn={batteryWarn} error={batteryError} />
        <HudDivider />
        <HudMetric label="Failsafe" value={d.failsafeShort} error={failsafeError} />
      </GlassPanel>

      {bottomLeftParts.length > 0 ? (
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
              fontFamily: MONO,
              fontSize: 11.5,
              fontWeight: 600,
              color: "common.white",
              lineHeight: 1.3,
              wordBreak: "break-word",
            }}
          >
            {bottomLeftParts.map((part, index) => (
              <React.Fragment key={part.text}>
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
              </React.Fragment>
            ))}
          </Typography>
        </GlassPanel>
      ) : null}

      {detectionSegments.length > 0 ? (
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
              fontFamily: MONO,
              fontSize: 11.5,
              fontWeight: 600,
              color: detection?.enabled ? "success.light" : "rgba(255,255,255,0.75)",
              lineHeight: 1.3,
              textAlign: "right",
            }}
          >
            {detectionSegments.map((segment, index) => (
              <React.Fragment key={segment}>
                {index > 0 ? (
                  <Box component="span" sx={{ color: "rgba(255,255,255,0.35)", mx: 0.6 }}>
                    ·
                  </Box>
                ) : null}
                <Box component="span">{segment}</Box>
              </React.Fragment>
            ))}
          </Typography>
        </GlassPanel>
      ) : null}

      <Box sx={{ position: "absolute", top: 8, right: 8, pointerEvents: "auto" }}>
        <IconButton
          size="small"
          aria-label={detailsOpen ? "Hide telemetry details" : "Show telemetry details"}
          onClick={() => setDetailsOpen((open) => !open)}
          sx={{
            ...GLASS,
            color: "common.white",
            width: 32,
            height: 32,
            "&:hover": { bgcolor: "rgba(0,0,0,0.52)" },
          }}
        >
          {detailsOpen ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
        </IconButton>
      </Box>

      <Collapse in={detailsOpen} orientation="horizontal">
        <Box
          sx={{
            position: "absolute",
            top: 8,
            right: 44,
            bottom: 8,
            width: 136,
            pointerEvents: "auto",
            overflowY: "auto",
            ...GLASS,
            px: 1,
            py: 0.85,
            display: "block",
          }}
        >
          <Typography
            sx={{
              fontSize: 8.5,
              fontWeight: 700,
              letterSpacing: 0.9,
              textTransform: "uppercase",
              color: "rgba(255,255,255,0.45)",
              mb: 0.75,
            }}
          >
            Details
          </Typography>
          <Stack spacing={0.65}>
            <DetailRow label="Wind" value={d.wind} />
            <DetailRow label="Heading" value={d.heading} />
            <DetailRow label="GPS" value={d.gpsStrength} />
            <DetailRow label="Battery" value={d.batteryHealth} warn={batteryWarn} error={batteryError} />
            <DetailRow label="Mode" value={d.mode} />
            <DetailRow label="Failsafe" value={d.failsafe} error={failsafeError} />
          </Stack>
          {detection ? (
            <>
              <Typography
                sx={{
                  fontSize: 8.5,
                  fontWeight: 700,
                  letterSpacing: 0.9,
                  textTransform: "uppercase",
                  color: "rgba(255,255,255,0.45)",
                  mt: 1,
                  mb: 0.5,
                }}
              >
                ML
              </Typography>
              <DetailRow label="Frames" value={String(detection.framesProcessed ?? 0)} />
              {detection.lastError ? <DetailRow label="Error" value={detection.lastError} error /> : null}
            </>
          ) : null}
        </Box>
      </Collapse>
    </Box>
  );
}

function DetailRow({
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
          fontFamily: MONO,
          fontSize: 11,
          fontWeight: 600,
          color: valueColor(warn, error),
          lineHeight: 1.25,
          wordBreak: "break-word",
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}
