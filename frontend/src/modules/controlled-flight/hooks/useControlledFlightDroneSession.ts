import { useCallback, useMemo, useRef, useState } from "react";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import { fetchFlightStatus } from "../../mission-runtime/api/missionsApi";
import { getToken } from "../../session";
import type { LatLng } from "../../../shared/utils/extractLatLng";
import { useControlledPreflight } from "./useControlledPreflight";
import { useManualFlightControls } from "./useManualFlightControls";
import type { ControlledFlightMissionStatus } from "../controlledFlightViewTypes";
import {
  telemetryBatteryPercent,
  telemetryBoolean,
  telemetryGpsFixType,
  telemetryHeartbeatReceived,
} from "../utils/telemetryHealth";

type UseControlledFlightDroneSessionOptions = {
  addError: (message: string) => void;
  notify: (message: string, severity?: "success" | "info" | "warning" | "error") => void;
  droneManualConnected: boolean;
  setDroneManualConnected: (connected: boolean) => void;
  missionStatus: ControlledFlightMissionStatus | null;
  activeFlightId: string | null;
  lastMissionId: string | null;
  telemetry: unknown;
  wsConnected: boolean;
  droneConnected: boolean;
  droneCenter: LatLng | null;
};

export function useControlledFlightDroneSession({
  addError,
  notify,
  droneManualConnected,
  setDroneManualConnected,
  missionStatus,
  activeFlightId,
  lastMissionId,
  telemetry,
  wsConnected,
  droneConnected,
  droneCenter,
}: UseControlledFlightDroneSessionOptions) {
  const [connecting, setConnecting] = useState(false);
  const stopAllManualRef = useRef<() => void>(() => {});

  const batteryPercent = useMemo(() => telemetryBatteryPercent(telemetry), [telemetry]);
  const gpsFixType = useMemo(() => telemetryGpsFixType(telemetry), [telemetry]);
  const heartbeatReceived = useMemo(() => telemetryHeartbeatReceived(telemetry), [telemetry]);
  const ekfOk = useMemo(() => telemetryBoolean(telemetry, ["ekf", "ok"]), [telemetry]);
  const compassHealthy = useMemo(() => telemetryBoolean(telemetry, ["compass", "healthy"]), [telemetry]);

  const connectDrone = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    setConnecting(true);
    try {
      await connectDroneTelemetry(token);
      setDroneManualConnected(true);
      notify("Drone telemetry connected.", "success");
    } catch (error: unknown) {
      addError(error instanceof Error ? error.message : "Connect failed");
    } finally {
      setConnecting(false);
    }
  }, [addError, notify, setDroneManualConnected]);

  const {
    controlledPreflight,
    manualControlEnabled,
    setManualControlEnabled,
    runControlledPreflightCheck,
  } = useControlledPreflight({
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
    onFailed: () => {
      setManualControlEnabled(false);
      stopAllManualRef.current();
    },
  });

  const runManualPreflightCheck = useCallback(async () => {
    const token = getToken();
    if (!token) {
      addError("Not authenticated");
      return;
    }
    setConnecting(true);
    try {
      if (!missionStatus?.telemetry?.running || !droneConnected) {
        await connectDroneTelemetry(token);
      }
      setDroneManualConnected(true);
      await new Promise((resolve) => window.setTimeout(resolve, 600));
      const refreshedStatus = await fetchFlightStatus<ControlledFlightMissionStatus>(token);
      runControlledPreflightCheck({
        droneConnected:
          droneConnected || Boolean(refreshedStatus?.orchestrator?.drone_connected),
        wsConnected: wsConnected || Boolean(refreshedStatus?.telemetry?.running),
        missionStatus: refreshedStatus,
      });
    } catch (error) {
      addError(error instanceof Error ? error.message : "Preflight check failed");
    } finally {
      setConnecting(false);
    }
  }, [
    addError,
    droneConnected,
    missionStatus?.telemetry?.running,
    runControlledPreflightCheck,
    setDroneManualConnected,
    wsConnected,
  ]);

  const manualControlReady = Boolean(
    controlledPreflight?.passed && droneManualConnected && (droneConnected || wsConnected),
  );

  const trackedMissionId = activeFlightId ?? lastMissionId;

  const manualControls = useManualFlightControls({
    flightId: trackedMissionId,
    enabled: manualControlEnabled,
    ready: manualControlReady,
    onDisable: () => setManualControlEnabled(false),
  });

  stopAllManualRef.current = manualControls.stopAllManualCommands;

  const droneReady = Boolean(droneManualConnected && droneConnected && droneCenter);

  return {
    droneManualConnected,
    connecting,
    connectDrone,
    controlledPreflight,
    manualControlEnabled,
    setManualControlEnabled,
    manualControlReady,
    runManualPreflightCheck,
    batteryPercent,
    gpsFixType,
    manualControls,
    droneReady,
  };
}
