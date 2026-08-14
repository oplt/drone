import { useMemo } from "react";
import { deriveTelemetry } from "../../utils/deriveTelemetry";
import { formatTelemetryHudModelName } from "./telemetryHudFormatters";
import type {
  DetectionHudInfo,
  TelemetryHudMissionPart,
} from "./telemetryHudTypes";

export type TelemetryHudModel = {
  derived: ReturnType<typeof deriveTelemetry>;
  batteryWarn: boolean;
  batteryError: boolean;
  gpsWarn: boolean;
  gpsError: boolean;
  statusError: boolean;
  failsafeError: boolean;
  bottomLeftParts: TelemetryHudMissionPart[];
  detectionSegments: string[];
};

export function useTelemetryHudModel(
  telemetry: unknown,
  cameraTitle: string,
  missionLabel: string | null | undefined,
  recordingStatus: string | null | undefined,
  detection: DetectionHudInfo | undefined,
): TelemetryHudModel {
  const derived = useMemo(() => deriveTelemetry(telemetry), [telemetry]);

  const batteryPct = useMemo(() => {
    const match = derived.batteryShort.match(/(\d+)/);
    return match ? Number.parseInt(match[1], 10) : null;
  }, [derived.batteryShort]);

  const batteryWarn = batteryPct !== null && batteryPct < 30;
  const batteryError = batteryPct !== null && batteryPct < 15;
  const gpsWarn = derived.gpsShort === "GPS NO FIX" || derived.gpsShort === "GPS 2D";
  const gpsError = derived.gpsShort === "GPS NO FIX";
  const statusError = derived.statusShort === "EMERGENCY" || derived.statusShort === "RTL";
  const failsafeError = derived.failsafeShort !== "SAFE";

  const bottomLeftParts = useMemo(
    () =>
      [
        { text: cameraTitle, emphasis: true },
        missionLabel ? { text: missionLabel } : null,
        recordingStatus ? { text: recordingStatus, dim: true } : null,
      ].filter(Boolean) as TelemetryHudMissionPart[],
    [cameraTitle, missionLabel, recordingStatus],
  );

  const modelShort = formatTelemetryHudModelName(detection?.modelName);
  const detectionSegments = useMemo(
    () =>
      [
        modelShort,
        detection?.fps != null ? `${detection.fps} FPS` : null,
        detection?.enabled ? "ON" : detection ? "OFF" : null,
      ].filter(Boolean) as string[],
    [modelShort, detection],
  );

  return {
    derived,
    batteryWarn,
    batteryError,
    gpsWarn,
    gpsError,
    statusError,
    failsafeError,
    bottomLeftParts,
    detectionSegments,
  };
}
