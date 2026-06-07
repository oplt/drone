import { useCallback, useEffect, useRef, useState } from "react";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import { startMissionWithPreflight, type PreflightRunResponse } from "../../mission-runtime";
import { getToken } from "../../session";
import { useManualFlightControls } from "../../controlled-flight/hooks/useManualFlightControls";
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
  wsConnected: boolean;
  droneConnected: boolean;
  warehouseMapId: number | null;
  sensorRigId: number | null;
  dockId: number | null;
  warehousePreflightPassed: boolean;
  setPendingFlightId: (flightId: string | null) => void;
  onPreflightRun: (preflight: PreflightRunResponse | null) => void;
  onMessage: (message: string) => void;
  onError: (message: string) => void;
  onScanResultReady?: (jobId: number) => void;
};

export function useWarehouseManualMapping({
  activeFlightId,
  wsConnected,
  droneConnected,
  warehouseMapId,
  sensorRigId,
  dockId,
  warehousePreflightPassed,
  setPendingFlightId,
  onPreflightRun,
  onMessage,
  onError,
  onScanResultReady,
}: WarehouseManualMappingHookArgs) {
  const [connecting, setConnecting] = useState(false);
  const [startingSession, setStartingSession] = useState(false);
  const [manualControlEnabled, setManualControlEnabled] = useState(false);
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
    }, activeFlightId ? 5000 : 15000);
    return () => window.clearInterval(interval);
  }, [refreshMappingStackStatus, activeFlightId]);

  useEffect(() => {
    if (!warehousePreflightPassed) {
      setManualControlEnabled(false);
      stopAllManualRef.current();
    }
  }, [warehousePreflightPassed]);

  const manualControlReady = Boolean(
    warehousePreflightPassed && activeFlightId && (droneConnected || wsConnected),
  );

  const disableManualControl = useCallback(() => {
    setManualControlEnabled(false);
  }, []);

  const manual = useManualFlightControls({
    flightId: activeFlightId,
    enabled: manualControlEnabled,
    ready: manualControlReady,
    onDisable: disableManualControl,
  });
  stopAllManualRef.current = manual.stopAllManualCommands;

  const connectDrone = useCallback(async () => {
    const token = getToken();
    if (!token) return onError("Not authenticated");
    setConnecting(true);
    try {
      await connectDroneTelemetry(token, "controlled", "indoor_local");
      onMessage("Drone telemetry connected.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Drone connection failed");
    } finally {
      setConnecting(false);
    }
  }, [onError, onMessage]);

  const startKeyboardSession = useCallback(async () => {
    if (!warehousePreflightPassed) {
      onError("Run Warehouse Preflight checks before starting keyboard flight.");
      return;
    }
    const token = getToken();
    if (!token) return onError("Not authenticated");
    setStartingSession(true);
    try {
      const { preflight: run, mission } = await startMissionWithPreflight(
        {
          name: "Warehouse Manual Mapping",
          cruise_alt: 2.5,
          mission_type: "controlled",
          flight_environment: "indoor_local",
        },
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
  }, [onError, onMessage, onPreflightRun, setPendingFlightId, warehousePreflightPassed]);

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
    startingSession,
    mappingBusy,
    mappingActiveFlightId,
    mappingStackStatus,
    manualControlReady,
    manualControlEnabled,
    setManualControlEnabled,
    manual,
    connectDrone,
    startKeyboardSession,
    startMapping,
    stopMapping,
  };
}
