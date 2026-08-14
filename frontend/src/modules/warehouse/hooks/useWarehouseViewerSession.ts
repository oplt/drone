import { useCallback, useEffect, useMemo } from "react";
import type { RefObject } from "react";
import type { MissionLifecycleState } from "../../mission-runtime";
import {
  buildStartScanTooltip,
  buildWarehouseSystemStatusItems,
} from "../utils/warehouseSystemStatus";
import type { useWarehouseMissionRuntimeController } from "./useWarehouseMissionRuntimeController";
import type { useWarehouseScannedMapActions } from "./useWarehouseScannedMapActions";
import { useWarehouseLiveVoxelMap } from "./useWarehouseLiveVoxelMap";
import { useWarehouseMappingStack } from "./useWarehouseMappingStack";
import { useWarehouseScannedMapReplay } from "./useWarehouseScannedMapReplay";
import { getToken } from "../../session";

type ViewerSessionOptions = {
  runtime: ReturnType<typeof useWarehouseMissionRuntimeController>;
  scanned: ReturnType<typeof useWarehouseScannedMapActions>;
  selectedWarehouseMapId: number | null;
  preflightPassed: boolean;
  authToken: string | null;
  viewerSectionRef: RefObject<HTMLDivElement | null>;
  previousMissionStateRef: RefObject<MissionLifecycleState | null>;
  notify: (message: string, severity: "success" | "info" | "error") => void;
  startingScan: boolean;
  selectedSensorRigId: number | null;
  sensorRigReady: boolean | undefined;
  perceptionReady: boolean | undefined;
};

export function useWarehouseViewerSession({
  runtime,
  scanned,
  selectedWarehouseMapId,
  preflightPassed,
  authToken,
  viewerSectionRef,
  previousMissionStateRef,
  notify,
  startingScan,
  selectedSensorRigId,
  sensorRigReady,
  perceptionReady,
}: ViewerSessionOptions) {
  const { loadScannedMaps } = scanned;
  const viewingScanReplay =
    Boolean(scanned.viewerScannedMap) && !runtime.activeFlightId;
  const missionState =
    runtime.missionStatus?.mission_lifecycle?.state ?? "idle";
  const liveVoxelMapSessionActive = Boolean(
    runtime.activeFlightId && preflightPassed,
  );
  const liveVoxelMap = useWarehouseLiveVoxelMap(runtime.activeFlightId, {
    enabled: Boolean(runtime.activeFlightId && !viewingScanReplay),
    token: authToken,
  });
  const { mappingStackStatus } = useWarehouseMappingStack({
    enabled: Boolean(runtime.activeFlightId),
    getToken,
  });
  const scannedMapReplay = useWarehouseScannedMapReplay(
    scanned.viewerScannedMap,
    authToken,
    { enabled: viewingScanReplay },
  );
  const displayedVoxelMap = viewingScanReplay
    ? scannedMapReplay.state
    : liveVoxelMapSessionActive
      ? liveVoxelMap
      : scannedMapReplay.state;

  useEffect(() => {
    void loadScannedMaps();
  }, [loadScannedMaps]);

  useEffect(() => {
    const state = runtime.missionStatus?.mission_lifecycle?.state ?? null;
    const previous = previousMissionStateRef.current;
    if (
      (previous === "running" || previous === "paused") &&
      (state === "completed" || state === "failed" || state === "aborted")
    ) {
      void loadScannedMaps();
    }
    previousMissionStateRef.current = state;
  }, [
    runtime.missionStatus?.mission_lifecycle?.state,
    loadScannedMaps,
    previousMissionStateRef,
  ]);

  const handleScanResultReady = useCallback(
    (jobId: number) => {
      void loadScannedMaps({ selectJobId: jobId, showInViewer: true }).then(
        () => {
          viewerSectionRef.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        },
      );
      notify(`Scan result #${jobId} saved to Previous Scan Results.`, "success");
    },
    [loadScannedMaps, notify, viewerSectionRef],
  );

  const startScanDisabled =
    startingScan || !selectedWarehouseMapId || selectedSensorRigId == null ||
    sensorRigReady !== true || !preflightPassed;
  const startScanTooltip = buildStartScanTooltip({
    warehousePreflightPassed: preflightPassed,
    selectedWarehouseMapId,
    selectedSensorRigId,
    sensorRigReady,
    perceptionReady,
  });

  const systemStatusItems = useMemo(
    () =>
      buildWarehouseSystemStatusItems({
        droneConnected: runtime.droneConnected,
        wsConnected: runtime.wsConnected,
        viewingScanReplay,
        scannedMapReplayHasData: scannedMapReplay.hasReplay,
        activeFlightId: runtime.activeFlightId,
        liveChunkCount: liveVoxelMap.chunks.length,
        warehousePreflightPassed: preflightPassed,
        missionState,
      }),
    [
      liveVoxelMap.chunks.length,
      missionState,
      preflightPassed,
      runtime.activeFlightId,
      runtime.droneConnected,
      runtime.wsConnected,
      scannedMapReplay.hasReplay,
      viewingScanReplay,
    ],
  );

  const visibleScannedMaps = useMemo(
    () => scanned.filterScannedMapsForWarehouse(selectedWarehouseMapId),
    [selectedWarehouseMapId, scanned],
  );

  const missionName =
    runtime.missionStatus?.mission_lifecycle?.mission_name ??
    runtime.missionStatus?.mission_name ??
    "No active warehouse mission";
  return {
    viewingScanReplay,
    missionState,
    liveVoxelMapSessionActive,
    liveVoxelMap,
    mappingStackStatus,
    scannedMapReplay,
    displayedVoxelMap,
    handleScanResultReady,
    startScanDisabled,
    startScanTooltip,
    systemStatusItems,
    visibleScannedMaps,
    missionName,
  };
}
