import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { Box, Collapse, IconButton, Stack, Typography } from "@mui/material";
import type { DerivedTelemetry } from "../../utils/deriveTelemetry";
import { DetailRow } from "./telemetryHudPrimitives";
import { TELEMETRY_HUD_GLASS } from "./telemetryHudStyles";
import type { DetectionHudInfo } from "./telemetryHudTypes";

type TelemetryHudDetailsDrawerProps = {
  detailsOpen: boolean;
  onToggle: () => void;
  derived: DerivedTelemetry;
  batteryWarn: boolean;
  batteryError: boolean;
  failsafeError: boolean;
  detection: DetectionHudInfo | undefined;
};

export function TelemetryHudDetailsDrawer({
  detailsOpen,
  onToggle,
  derived,
  batteryWarn,
  batteryError,
  failsafeError,
  detection,
}: TelemetryHudDetailsDrawerProps) {
  return (
    <>
      <Box sx={{ position: "absolute", top: 8, right: 8, pointerEvents: "auto" }}>
        <IconButton
          size="small"
          aria-label={detailsOpen ? "Hide telemetry details" : "Show telemetry details"}
          onClick={onToggle}
          sx={{
            ...TELEMETRY_HUD_GLASS,
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
            ...TELEMETRY_HUD_GLASS,
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
            <DetailRow label="Wind" value={derived.wind} />
            <DetailRow label="Heading" value={derived.heading} />
            <DetailRow label="GPS" value={derived.gpsStrength} />
            <DetailRow
              label="Battery"
              value={derived.batteryHealth}
              warn={batteryWarn}
              error={batteryError}
            />
            <DetailRow label="Mode" value={derived.mode} />
            <DetailRow label="Failsafe" value={derived.failsafe} error={failsafeError} />
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
              {detection.lastError ? (
                <DetailRow label="Error" value={detection.lastError} error />
              ) : null}
            </>
          ) : null}
        </Box>
      </Collapse>
    </>
  );
}
