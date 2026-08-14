import type { RefObject } from "react";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import { WarehouseMobileConfigPane } from "./WarehouseMobileConfigPane";
import { WarehousePageShell } from "./WarehousePageShell";
import { WarehouseScenePane } from "./WarehouseScenePane";
import { WarehouseStatusPane } from "./WarehouseStatusPane";
import type { useWarehouseViewerSession } from "../hooks/useWarehouseViewerSession";
import type { useWarehouseDrawerCoordinator } from "../hooks/useWarehouseDrawerCoordinator";
import type { useWarehouseMapPlacement } from "../hooks/useWarehouseMapPlacement";
import type { useWarehouseMaps } from "../hooks/useWarehouseMaps";
import type { useWarehouseMissionRuntimeController } from "../hooks/useWarehouseMissionRuntimeController";
import type { useWarehouseScannedMapActions } from "../hooks/useWarehouseScannedMapActions";
import type { WarehousePageState } from "../warehousePageState";
import { getWarehouseName } from "../scannedMapSelectors";
import type { WarehouseSystemStatusItem } from "../utils/warehouseSystemStatus";
import type { WarehouseSensorRigHealth } from "../types";

type WarehousePageMainSectionProps = {
  systemStatusItems: WarehouseSystemStatusItem[];
  maps: ReturnType<typeof useWarehouseMaps>;
  rigs: {
    selectedSensorRigId: number | null;
    sensorRigHealth: WarehouseSensorRigHealth | null | undefined;
  };
  selectedDockId: number | null;
  preflight: WarehouseGoPreflight | null;
  runtime: ReturnType<typeof useWarehouseMissionRuntimeController>;
  errors: string[];
  onDismissError: (index: number) => void;
  onClearErrors: () => void;
  mobileLayout: boolean;
  mobileTab: "status" | "scene" | "config";
  onMobileTabChange: (tab: "status" | "scene" | "config") => void;
  apiBase: string;
  authToken: string | null;
  viewerSectionRef: RefObject<HTMLDivElement | null>;
  viewer: ReturnType<typeof useWarehouseViewerSession>;
  scanned: ReturnType<typeof useWarehouseScannedMapActions>;
  scannedMapsLoading: boolean;
  drawers: ReturnType<typeof useWarehouseDrawerCoordinator>;
  warehouseMapPlacement: ReturnType<typeof useWarehouseMapPlacement>;
  mapDetailTab: WarehousePageState["mapDetailTab"];
  onMapDetailTabChange: (tab: WarehousePageState["mapDetailTab"]) => void;
  onError: (message: string) => void;
  onOpenSetup: () => void;
  onOpenChecks: () => void;
  onOpenMission: () => void;
  setDeleteTarget: (target: WarehousePageState["deleteTarget"]) => void;
};

export function WarehousePageMainSection({
  systemStatusItems,
  maps,
  rigs,
  selectedDockId,
  preflight,
  runtime,
  errors,
  onDismissError,
  onClearErrors,
  mobileLayout,
  mobileTab,
  onMobileTabChange,
  apiBase,
  authToken,
  viewerSectionRef,
  viewer,
  scanned,
  scannedMapsLoading,
  drawers,
  warehouseMapPlacement,
  mapDetailTab,
  onMapDetailTabChange,
  onError,
  onOpenSetup,
  onOpenChecks,
  onOpenMission,
  setDeleteTarget,
}: WarehousePageMainSectionProps) {
  const {
    viewingScanReplay,
    liveVoxelMapSessionActive,
    liveVoxelMap,
    mappingStackStatus,
    scannedMapReplay,
    displayedVoxelMap,
    visibleScannedMaps,
  } = viewer;

  return (
    <WarehousePageShell
      systemStatusItems={systemStatusItems}
      hasMap={maps.selectedWarehouseMapId != null}
      hasRig={rigs.selectedSensorRigId != null}
      hasDock={selectedDockId != null}
      preflight={preflight}
      droneConnected={runtime.droneConnected}
      activeFlightId={runtime.activeFlightId}
      sensorRigHealth={rigs.sensorRigHealth ?? null}
      mappingStatus={runtime.missionStatus?.warehouse_mapping}
      liveHealth={liveVoxelMap.health}
      errors={errors}
      onDismissError={onDismissError}
      onClearErrors={onClearErrors}
      mobileLayout={mobileLayout}
      mobileTab={mobileTab}
      onMobileTabChange={onMobileTabChange}
      statusPane={
        <WarehouseStatusPane
          title="Warehouse Camera"
          imgAlt="Warehouse camera stream"
          disconnectedMessage="Waiting for mission video stream"
          frameHeight={mobileLayout ? 280 : 600}
          frameSx={{
            minHeight: mobileLayout ? 280 : 600,
            height: mobileLayout ? 280 : 600,
          }}
          apiBase={apiBase}
          streamKey={runtime.streamKey}
          videoToken={authToken}
          startingVideo={runtime.startingVideo}
          videoError={runtime.videoError}
          videoRetryCount={runtime.videoRetryCount}
          droneConnected={runtime.droneConnected}
          telemetry={runtime.telemetry}
          onVideoError={runtime.handleVideoError}
          onVideoLoad={runtime.handleVideoLoad}
          onRetry={runtime.retryVideo}
        />
      }
      scenePane={
        <WarehouseScenePane
          sectionRef={viewerSectionRef}
          selectorProps={{
            maps: visibleScannedMaps,
            selectedMap: scanned.selectedScannedMap,
            loading: scannedMapsLoading,
            disabled: viewingScanReplay && scannedMapReplay.loading,
            deleting: scanned.deletingScannedMap,
            onSelect: (jobId) => {
              scanned.setSelectedMapJobId(jobId);
              scanned.setViewerMapJobId(jobId);
            },
            onRefresh: () => void scanned.loadScannedMaps(),
            onDelete: () => {
              if (!scanned.selectedScannedMap) return;
              const selectedScannedMap = scanned.selectedScannedMap;
              setDeleteTarget({
                kind: "scan result",
                label: `${getWarehouseName(selectedScannedMap)} (#${selectedScannedMap.job_id})`,
                onConfirm: () => {
                  void scanned
                    .handleDeleteScannedMap(selectedScannedMap)
                    .finally(() => setDeleteTarget(null));
                },
              });
            },
          }}
          showViewer={
            Boolean(scanned.viewerScannedMap) || liveVoxelMapSessionActive
          }
          replayMode={viewingScanReplay}
          viewerProps={{
            flightId: viewingScanReplay
              ? (scannedMapReplay.replayFlightId ??
                displayedVoxelMap.latestUpdate?.flight_id ??
                null)
              : (runtime.activeFlightId ??
                displayedVoxelMap.latestUpdate?.flight_id ??
                null),
            state: displayedVoxelMap,
            cacheMode: viewingScanReplay ? "replay" : undefined,
            mapMode: viewingScanReplay ? "replay" : "live",
            scannedMapId: viewingScanReplay ? scannedMapReplay.scannedMapId : null,
            onReloadReplay: viewingScanReplay
              ? scannedMapReplay.reloadFromDiskManifest
              : undefined,
            mappingStatus: viewingScanReplay
              ? null
              : (runtime.missionStatus?.warehouse_mapping ?? null),
            mappingStackStatus: viewingScanReplay ? null : mappingStackStatus,
            hidden:
              (drawers.setup.open ||
                drawers.checks.open ||
                drawers.mission.open) &&
              !warehouseMapPlacement.viewerProps.pickMode &&
              mapDetailTab !== "coordinateSetup",
            mapPlacement: warehouseMapPlacement.viewerProps,
            warehouseMapId: maps.selectedWarehouseMapId,
            mapPlacementPanel: warehouseMapPlacement.panelProps,
            mapDetailTab,
            onMapDetailTabChange,
            onCoordinateSetupError: onError,
            coordinateSetupToken: authToken,
            replayLoading: viewingScanReplay && scannedMapReplay.loading,
            onClearMap: viewingScanReplay ? undefined : liveVoxelMap.clearMap,
            onToggleStream: viewingScanReplay
              ? undefined
              : liveVoxelMap.toggleStreamPaused,
            streamPaused: viewingScanReplay ? false : liveVoxelMap.streamPaused,
          }}
        />
      }
      mobileConfigPane={
        <WarehouseMobileConfigPane
          onOpenSetup={onOpenSetup}
          onOpenChecks={onOpenChecks}
          onOpenMission={onOpenMission}
        />
      }
    />
  );
}
