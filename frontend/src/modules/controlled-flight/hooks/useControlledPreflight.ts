import { useCallback, useState } from "react";
import type { LatLng } from "../../../shared/utils/extractLatLng";
import type { ControlledPreflightResult } from "../types";

type MissionStatusLike = {
  orchestrator?: { drone_connected?: boolean };
  telemetry?: {
    running?: boolean;
    source_connected?: boolean;
    has_position_data?: boolean;
  };
};

type ControlledPreflightProfile = "outdoor" | "warehouse";

type ControlledPreflightInputs = {
  droneConnected: boolean;
  wsConnected: boolean;
  missionStatus: MissionStatusLike | null;
  droneCenter: LatLng | null;
  heartbeatReceived: boolean;
  gpsFixType: number | null;
  ekfOk: boolean | null;
  compassHealthy: boolean | null;
  batteryPercent: number | null;
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
  profile = "outdoor",
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
  profile?: ControlledPreflightProfile;
}) {
  const [controlledPreflight, setControlledPreflight] =
    useState<ControlledPreflightResult | null>(null);
  const [manualControlEnabled, setManualControlEnabled] = useState(false);

  const runControlledPreflightCheck = useCallback((overrides?: Partial<ControlledPreflightInputs>) => {
    const input = {
      droneConnected,
      wsConnected,
      missionStatus,
      droneCenter,
      heartbeatReceived,
      gpsFixType,
      ekfOk,
      compassHealthy,
      batteryPercent,
      ...overrides,
    };
    const telemetryRunning = Boolean(
      input.wsConnected &&
        (input.missionStatus?.telemetry?.running ??
          input.missionStatus?.telemetry?.source_connected ??
          true),
    );
    const vehicleLinked = Boolean(
      input.droneConnected || input.missionStatus?.orchestrator?.drone_connected,
    );
    const hasPosition = Boolean(input.missionStatus?.telemetry?.has_position_data || input.droneCenter);
    const telemetryHasVehicleData = telemetryRunning && hasPosition;
    const inferredGpsFixType =
      input.gpsFixType ?? (telemetryHasVehicleData ? 3 : null);
    const gpsRequired = profile === "outdoor";
    const ekfRequired = profile === "outdoor";
    const compassRequired = profile === "outdoor";
    const checks = [
      {
        id: "drone-link",
        label: "Drone link",
        ok: vehicleLinked,
        detail:
          vehicleLinked
            ? "Vehicle is connected to the orchestrator."
            : "No active vehicle connection detected.",
      },
      {
        id: "telemetry",
        label: "Telemetry stream",
        ok: telemetryRunning,
        detail:
          telemetryRunning
            ? "Telemetry stream is live."
            : "Telemetry stream is not running yet. Connect drone telemetry first.",
      },
      {
        id: "position",
        label: profile === "warehouse" ? "Local pose" : "Position lock",
        ok: profile === "warehouse" ? true : hasPosition,
        detail:
          profile === "warehouse"
            ? hasPosition
              ? "Live pose data is available for warehouse mapping."
              : "Warehouse mode can start without GPS; ROS/VIO pose is validated by the mapping bridge."
            : hasPosition
            ? "Live position data is available."
            : "No valid position fix is available.",
      },
      {
        id: "heartbeat",
        label: "Heartbeat",
        ok: input.heartbeatReceived || (telemetryRunning && vehicleLinked),
        detail: input.heartbeatReceived
          ? "Heartbeat received from vehicle."
          : telemetryRunning && vehicleLinked
            ? "Telemetry is live; heartbeat timestamp is not exposed by this adapter."
          : "No heartbeat from vehicle.",
      },
      {
        id: "gps-fix",
        label: "GPS fix",
        ok: gpsRequired ? inferredGpsFixType != null && inferredGpsFixType >= 3 : true,
        detail:
          !gpsRequired
            ? "Not required for indoor warehouse mapping; use ROS/VIO/local pose."
            : input.gpsFixType == null && telemetryHasVehicleData
              ? "GPS fix type is not exposed, but live position data is available."
              : inferredGpsFixType == null
                ? "No GPS fix data received."
                : `GPS fix type ${inferredGpsFixType} (${inferredGpsFixType >= 3 ? "3D fix" : "insufficient"}).`,
      },
      {
        id: "ekf",
        label: "EKF status",
        ok: ekfRequired ? input.ekfOk !== false && telemetryHasVehicleData : true,
        detail:
          !ekfRequired && input.ekfOk == null
            ? "Not exposed by this warehouse adapter; mapping bridge health handles estimator readiness."
            : ekfRequired && input.ekfOk == null && telemetryHasVehicleData
              ? "EKF flag is not exposed; live position telemetry is available."
            : input.ekfOk == null
            ? "No EKF data received."
            : input.ekfOk
              ? "EKF estimates are healthy."
              : "EKF variance too high — not safe to arm.",
      },
      {
        id: "compass",
        label: "Compass",
        ok: compassRequired ? input.compassHealthy !== false && telemetryHasVehicleData : true,
        detail:
          !compassRequired && input.compassHealthy == null
            ? "Not required for indoor warehouse mapping; avoid magnetic gating near racks."
            : compassRequired && input.compassHealthy == null && telemetryHasVehicleData
              ? "Compass health flag is not exposed; live position telemetry is available."
            : input.compassHealthy == null
            ? "No compass data received."
            : input.compassHealthy
              ? "Compass magnetic field in normal range."
              : "Compass reading abnormal — check for interference.",
      },
      {
        id: "battery",
        label: "Battery level",
        ok: input.batteryPercent == null ? true : input.batteryPercent >= 20,
        detail:
          input.batteryPercent == null
            ? "Battery percentage not exposed by telemetry."
            : `${input.batteryPercent.toFixed(0)}% remaining.`,
      },
    ];

    const passed = checks.every((check) => check.ok);
    setControlledPreflight({ ranAt: new Date().toISOString(), passed, checks });
    if (!passed) {
      setManualControlEnabled(false);
      onFailed();
    }
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
    profile,
    wsConnected,
  ]);

  void telemetry;

  return {
    controlledPreflight,
    manualControlEnabled,
    setManualControlEnabled,
    runControlledPreflightCheck,
  };
}
