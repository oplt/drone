import { useCallback, useEffect, useRef, useState } from "react";
import type { LatLng } from "../../../shared/utils/extractLatLng";
import type { ControlledPreflightResult } from "../types";

type MissionStatusLike = {
  orchestrator?: { drone_connected?: boolean };
  telemetry?: {
    running?: boolean;
    has_position_data?: boolean;
  };
};

export function useControlledPreflight({
  droneConnected,
  wsConnected,
  missionStatus,
  droneCenter,
  heartbeatReceived,
  gpsFixType,
  ekfOk,
  compassHealthy,
  batteryPercent,
  telemetry,
  onFailed,
}: {
  droneConnected: boolean;
  wsConnected: boolean;
  missionStatus: MissionStatusLike | null;
  droneCenter: LatLng | null;
  heartbeatReceived: boolean;
  gpsFixType: number | null;
  ekfOk: boolean | null;
  compassHealthy: boolean | null;
  batteryPercent: number | null;
  telemetry: unknown;
  onFailed: () => void;
}) {
  const [controlledPreflight, setControlledPreflight] =
    useState<ControlledPreflightResult | null>(null);
  const [manualControlEnabled, setManualControlEnabled] = useState(false);

  const runControlledPreflightCheck = useCallback(() => {
    const checks = [
      {
        id: "drone-link",
        label: "Drone link",
        ok: Boolean(droneConnected || missionStatus?.orchestrator?.drone_connected),
        detail:
          droneConnected || missionStatus?.orchestrator?.drone_connected
            ? "Vehicle is connected to the orchestrator."
            : "No active vehicle connection detected.",
      },
      {
        id: "telemetry",
        label: "Telemetry stream",
        ok: Boolean(wsConnected && (missionStatus?.telemetry?.running ?? true)),
        detail:
          wsConnected && (missionStatus?.telemetry?.running ?? true)
            ? "Telemetry stream is live."
            : "Telemetry stream is not running yet.",
      },
      {
        id: "position",
        label: "Position lock",
        ok: Boolean(missionStatus?.telemetry?.has_position_data || droneCenter),
        detail:
          missionStatus?.telemetry?.has_position_data || droneCenter
            ? "Live position data is available."
            : "No valid position fix is available.",
      },
      {
        id: "heartbeat",
        label: "Heartbeat",
        ok: heartbeatReceived,
        detail: heartbeatReceived
          ? "Heartbeat received from vehicle."
          : "No heartbeat from vehicle.",
      },
      {
        id: "gps-fix",
        label: "GPS fix",
        ok: gpsFixType == null ? false : gpsFixType >= 3,
        detail:
          gpsFixType == null
            ? "No GPS fix data received."
            : `GPS fix type ${gpsFixType} (${gpsFixType >= 3 ? "3D fix" : "insufficient"}).`,
      },
      {
        id: "ekf",
        label: "EKF status",
        ok: ekfOk == null ? false : ekfOk,
        detail:
          ekfOk == null
            ? "No EKF data received."
            : ekfOk
              ? "EKF estimates are healthy."
              : "EKF variance too high — not safe to arm.",
      },
      {
        id: "compass",
        label: "Compass",
        ok: compassHealthy == null ? false : compassHealthy,
        detail:
          compassHealthy == null
            ? "No compass data received."
            : compassHealthy
              ? "Compass magnetic field in normal range."
              : "Compass reading abnormal — check for interference.",
      },
      {
        id: "battery",
        label: "Battery level",
        ok: batteryPercent == null ? true : batteryPercent >= 20,
        detail:
          batteryPercent == null
            ? "Battery percentage not exposed by telemetry."
            : `${batteryPercent.toFixed(0)}% remaining.`,
      },
    ];

    const passed = checks.every((check) => check.ok);
    setControlledPreflight({ ranAt: new Date().toISOString(), passed, checks });
    if (!passed) {
      setManualControlEnabled(false);
      onFailed();
      return;
    }
    setManualControlEnabled(true);
  }, [
    batteryPercent,
    compassHealthy,
    droneCenter,
    droneConnected,
    ekfOk,
    gpsFixType,
    heartbeatReceived,
    missionStatus,
    onFailed,
    wsConnected,
  ]);

  const prevTelemetryRef = useRef(telemetry);
  useEffect(() => {
    if (telemetry && telemetry !== prevTelemetryRef.current) {
      prevTelemetryRef.current = telemetry;
      runControlledPreflightCheck();
    }
  }, [runControlledPreflightCheck, telemetry]);

  return {
    controlledPreflight,
    manualControlEnabled,
    setManualControlEnabled,
    runControlledPreflightCheck,
  };
}
