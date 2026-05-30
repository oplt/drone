import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { queryClient } from "../../../app/providers/queryClient";
import { missionKeys } from "../../../app/config/queryKeys";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import { startMissionWithPreflight, type PreflightRunResponse } from "../../mission-runtime";
import { fetchFlightStatus } from "../../mission-runtime/api/missionsApi";
import { getToken } from "../../session";
import { useDroneCenter } from "../../maps";
import { useControlledPreflight } from "../../controlled-flight/hooks/useControlledPreflight";
import { useManualFlightControls } from "../../controlled-flight/hooks/useManualFlightControls";
import {
  telemetryBatteryPercent,
  telemetryBoolean,
  telemetryGpsFixType,
  telemetryHeartbeatReceived,
} from "../../controlled-flight/utils/telemetryHealth";
import {
  fetchWarehouseMappingStackStatus,
  startWarehouseManualMapping,
  stopWarehouseManualMapping,
  type WarehouseMappingStackStatus,
} from "../api/warehouseMissionsApi";

type MissionStatusLike = {
  orchestrator?: { drone_connected?: boolean };
  telemetry?: { running?: boolean; has_position_data?: boolean };
};

export type WarehouseManualMappingHookArgs = {
  activeFlightId: string | null;
  missionStatus: MissionStatusLike | null;
  telemetry: unknown;
  wsConnected: boolean;
  droneConnected: boolean;
  warehouseMapId: number | null;
  sensorRigId: number | null;
  dockId: number | null;
  setPendingFlightId: (flightId: string | null) => void;
  onPreflightRun: (preflight: PreflightRunResponse | null) => void;
  onMessage: (message: string) => void;
  onError: (message: string) => void;
  onScanResultReady?: (jobId: number) => void;
};

export function useWarehouseManualMapping({
  activeFlightId,
  missionStatus,
  telemetry,
  wsConnected,
  droneConnected,
  warehouseMapId,
  sensorRigId,
  dockId,
  setPendingFlightId,
  onPreflightRun,
  onMessage,
  onError,
  onScanResultReady,
}: WarehouseManualMappingHookArgs) {
  const [connecting, setConnecting] = useState(false);
  const [startingSession, setStartingSession] = useState(false);
  const [mappingActiveFlightId, setMappingActiveFlightId] = useState<string | null>(null);
  const [mappingBusy, setMappingBusy] = useState(false);
  const [mappingStackStatus, setMappingStackStatus] =
    useState<WarehouseMappingStackStatus | null>(null);
  const stopAllManualRef = useRef<() => void>(() => {});

  const refreshMappingStackStatus = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const status = await fetchWarehouseMappingStackStatus(token);
      setMappingStackStatus(status);
    } catch {
      setMappingStackStatus(null);
    }
  }, []);

  useEffect(() => {
    void refreshMappingStackStatus();
    const interval = window.setInterval(() => {
      void refreshMappingStackStatus();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [refreshMappingStackStatus]);

  const droneCenter = useDroneCenter(telemetry);
  const batteryPercent = useMemo(() => telemetryBatteryPercent(telemetry), [telemetry]);
  const gpsFixType = useMemo(() => telemetryGpsFixType(telemetry), [telemetry]);
  const heartbeatReceived = useMemo(() => telemetryHeartbeatReceived(telemetry), [telemetry]);
  const ekfOk = useMemo(() => telemetryBoolean(telemetry, ["ekf", "ok"]), [telemetry]);
  const compassHealthy = useMemo(
    () => telemetryBoolean(telemetry, ["compass", "healthy"]),
    [telemetry],
  );

  const preflight = useControlledPreflight({
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
    profile: "warehouse",
    onFailed: () => {
      stopAllManualRef.current();
    },
  });

  const manualControlReady = Boolean(
    preflight.controlledPreflight?.passed && activeFlightId && (droneConnected || wsConnected),
  );
  const setManualControlEnabled = preflight.setManualControlEnabled;
  const disableManualControl = useCallback(() => {
    setManualControlEnabled(false);
  }, [setManualControlEnabled]);

  const manual = useManualFlightControls({
    flightId: activeFlightId,
    enabled: preflight.manualControlEnabled,
    ready: manualControlReady,
    onDisable: disableManualControl,
  });
  stopAllManualRef.current = manual.stopAllManualCommands;

  const connectDrone = useCallback(async () => {
    const token = getToken();
    if (!token) return onError("Not authenticated");
    setConnecting(true);
    try {
      await connectDroneTelemetry(token);
      onMessage("Drone telemetry connected.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Drone connection failed");
    } finally {
      setConnecting(false);
    }
  }, [onError, onMessage]);

  const runPreflightCheck = useCallback(async () => {
    const token = getToken();
    if (!token) {
      onError("Not authenticated");
      return;
    }

    setConnecting(true);
    try {
      if (!missionStatus?.telemetry?.running || !droneConnected) {
        await connectDroneTelemetry(token);
      }
      const refreshedStatus = await queryClient.fetchQuery({
        queryKey: missionKeys.flightStatus(),
        queryFn: () => fetchFlightStatus<MissionStatusLike>(token),
        staleTime: 0,
      });
      preflight.runControlledPreflightCheck({
        droneConnected:
          droneConnected || Boolean(refreshedStatus?.orchestrator?.drone_connected),
        wsConnected,
        missionStatus: refreshedStatus,
      });
      onMessage("Warehouse preflight check completed.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Warehouse preflight failed");
    } finally {
      setConnecting(false);
    }
  }, [droneConnected, missionStatus?.telemetry?.running, onError, onMessage, preflight, wsConnected]);

  const startKeyboardSession = useCallback(async () => {
    const token = getToken();
    if (!token) return onError("Not authenticated");
    setStartingSession(true);
    try {
      const { preflight: run, mission } = await startMissionWithPreflight(
        { name: "Warehouse Manual Mapping", cruise_alt: 2.5, mission_type: "controlled" },
        token,
      );
      onPreflightRun(run);
      setPendingFlightId(mission.flight_id ?? null);
      onMessage("Keyboard flight session started.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Keyboard flight session failed");
    } finally {
      setStartingSession(false);
    }
  }, [onError, onMessage, onPreflightRun, setPendingFlightId]);

  const startMapping = useCallback(async () => {
    const token = getToken();
    if (!token || !activeFlightId || warehouseMapId == null) return;
    setMappingBusy(true);
    try {
      const result = await startWarehouseManualMapping(
        {
          flight_id: activeFlightId,
          warehouse_map_id: warehouseMapId,
          sensor_rig_id: sensorRigId,
          dock_id: dockId,
        },
        token,
      );
      setMappingActiveFlightId(activeFlightId);
      await refreshMappingStackStatus();
      onMessage(`Manual ROS mapping ${result.status}.`);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Manual mapping could not start");
    } finally {
      setMappingBusy(false);
    }
  }, [
    activeFlightId,
    dockId,
    onError,
    onMessage,
    refreshMappingStackStatus,
    sensorRigId,
    warehouseMapId,
  ]);

  const stopMapping = useCallback(async () => {
    const token = getToken();
    const flightId = mappingActiveFlightId ?? activeFlightId;
    if (!token || !flightId) return;
    setMappingBusy(true);
    try {
      const result = await stopWarehouseManualMapping(
        {
          flight_id: flightId,
          warehouse_map_id: warehouseMapId,
        },
        token,
      );
      setMappingActiveFlightId(null);
      await refreshMappingStackStatus();
      const jobId = result.mapping_job?.job_id;
      if (typeof jobId === "number" && Number.isFinite(jobId)) {
        onScanResultReady?.(jobId);
        onMessage(`Manual ROS mapping stopped. Scan result #${jobId} saved.`);
      } else if (result.mapping_job?.error) {
        onError(`Mapping stopped but result was not saved: ${result.mapping_job.error}`);
      } else if (!result.accepted) {
        onError(
          result.detail ??
            "Mapping stopped but the capture session could not be finalized for storage.",
        );
      } else {
        onMessage(`Manual ROS mapping ${result.status}.`);
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : "Manual mapping could not stop");
    } finally {
      setMappingBusy(false);
    }
  }, [
    activeFlightId,
    mappingActiveFlightId,
    onError,
    onMessage,
    onScanResultReady,
    refreshMappingStackStatus,
    warehouseMapId,
  ]);

  return {
    connecting,
    preflightPreparing: connecting,
    startingSession,
    mappingBusy,
    mappingActiveFlightId,
    mappingStackStatus,
    manualControlReady,
    preflight,
    manual,
    connectDrone,
    runPreflightCheck,
    startKeyboardSession,
    startMapping,
    stopMapping,
  };
}
