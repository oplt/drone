import { useState } from "react";
import { Box } from "@mui/material";
import { TelemetryHudDetectionPanel } from "./telemetryHud/TelemetryHudDetectionPanel";
import { TelemetryHudDetailsDrawer } from "./telemetryHud/TelemetryHudDetailsDrawer";
import { TelemetryHudMissionPanel } from "./telemetryHud/TelemetryHudMissionPanel";
import { TelemetryHudTopBar } from "./telemetryHud/TelemetryHudTopBar";
import type { TelemetryHudProps } from "./telemetryHud/telemetryHudTypes";
import { useTelemetryHudModel } from "./telemetryHud/useTelemetryHudModel";

export type { DetectionHudInfo, TelemetryHudProps } from "./telemetryHud/telemetryHudTypes";

export function TelemetryHud({
  telemetry,
  cameraTitle = "Survey Camera",
  missionLabel,
  recordingStatus,
  detection,
  sx,
}: TelemetryHudProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const model = useTelemetryHudModel(
    telemetry,
    cameraTitle,
    missionLabel,
    recordingStatus,
    detection,
  );

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
      <TelemetryHudTopBar
        derived={model.derived}
        detailsOpen={detailsOpen}
        statusError={model.statusError}
        gpsWarn={model.gpsWarn}
        gpsError={model.gpsError}
        batteryWarn={model.batteryWarn}
        batteryError={model.batteryError}
        failsafeError={model.failsafeError}
      />
      <TelemetryHudMissionPanel parts={model.bottomLeftParts} />
      <TelemetryHudDetectionPanel
        segments={model.detectionSegments}
        detection={detection}
        detailsOpen={detailsOpen}
      />
      <TelemetryHudDetailsDrawer
        detailsOpen={detailsOpen}
        onToggle={() => setDetailsOpen((open) => !open)}
        derived={model.derived}
        batteryWarn={model.batteryWarn}
        batteryError={model.batteryError}
        failsafeError={model.failsafeError}
        detection={detection}
      />
    </Box>
  );
}
