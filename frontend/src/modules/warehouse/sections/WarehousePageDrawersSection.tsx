import type { Dispatch, SetStateAction } from "react";
import type { PreflightRunResponse } from "../../mission-runtime";
import { getToken } from "../../session";
import { WarehouseDeleteConfirmationDialog } from "../components/WarehouseDeleteConfirmationDialog";
import type { useWarehouseViewerSession } from "../hooks/useWarehouseViewerSession";
import type { useWarehouseDrawerCoordinator } from "../hooks/useWarehouseDrawerCoordinator";
import type { useWarehouseFlightReadiness } from "../hooks/useWarehouseFlightReadiness";
import type { useWarehouseMapPlacement } from "../hooks/useWarehouseMapPlacement";
import type { useWarehouseMaps } from "../hooks/useWarehouseMaps";
import type { useWarehouseMissionDefaults } from "../hooks/useWarehouseMissionDefaults";
import type { useWarehouseMissionRuntimeController } from "../hooks/useWarehouseMissionRuntimeController";
import type { useRunWarehousePreflight } from "../hooks/useRunWarehousePreflight";
import type { useWarehouseScanActions } from "../hooks/useWarehouseScanActions";
import type { useWarehouseScannedMapActions } from "../hooks/useWarehouseScannedMapActions";
import type { useWarehouseSensorRigs } from "../hooks/useWarehouseSensorRigs";
import type { WarehouseFlyMode } from "../components/WarehouseFlyDrawerContent";
import type { WarehousePageState } from "../warehousePageState";
import type { WarehouseScannedMapResponse } from "../types/missions";
import { WarehouseChecksDrawer } from "./WarehouseChecksDrawer";
import { WarehouseMissionDrawer } from "./WarehouseMissionDrawer";
import { WarehouseSetupDrawer } from "./WarehouseSetupDrawer";

type WarehousePageDrawersSectionProps = {
  drawers: ReturnType<typeof useWarehouseDrawerCoordinator>;
  setupTab: WarehousePageState["setupTab"];
  onSetupTabChange: (tab: WarehousePageState["setupTab"]) => void;
  maps: ReturnType<typeof useWarehouseMaps>;
  scannedMaps: WarehouseScannedMapResponse[];
  rigs: ReturnType<typeof useWarehouseSensorRigs>;
  selectedDockId: number | null;
  onSelectedDockIdChange: (dockId: number | null) => void;
  onError: (message: string) => void;
  defaults: ReturnType<typeof useWarehouseMissionDefaults>;
  preflight: ReturnType<typeof useRunWarehousePreflight>;
  missionLoadedForReadiness: boolean;
  flyMode: WarehouseFlyMode;
  onFlyModeChange: Dispatch<SetStateAction<WarehouseFlyMode>>;
  viewer: ReturnType<typeof useWarehouseViewerSession>;
  runtime: ReturnType<typeof useWarehouseMissionRuntimeController>;
  flightReadiness: ReturnType<typeof useWarehouseFlightReadiness>;
  scanActions: ReturnType<typeof useWarehouseScanActions>;
  warehouseMapPlacement: ReturnType<typeof useWarehouseMapPlacement>;
  authToken: string | null;
  scanned: ReturnType<typeof useWarehouseScannedMapActions>;
  deleteTarget: WarehousePageState["deleteTarget"];
  onDeleteTargetChange: (target: WarehousePageState["deleteTarget"]) => void;
  onManualMappingMessage: (message: string) => void;
  onManualMappingPreflightRun: (preflight: PreflightRunResponse | null) => void;
};

export function WarehousePageDrawersSection({
  drawers,
  setupTab,
  onSetupTabChange,
  maps,
  scannedMaps,
  rigs,
  selectedDockId,
  onSelectedDockIdChange,
  onError,
  defaults,
  preflight,
  missionLoadedForReadiness,
  flyMode,
  onFlyModeChange,
  viewer,
  runtime,
  flightReadiness,
  scanActions,
  warehouseMapPlacement,
  authToken,
  scanned,
  deleteTarget,
  onDeleteTargetChange,
  onManualMappingMessage,
  onManualMappingPreflightRun,
}: WarehousePageDrawersSectionProps) {
  const {
    missionName,
    missionState,
    startScanDisabled,
    startScanTooltip,
    handleScanResultReady,
  } = viewer;

  return (
    <>
      <WarehouseSetupDrawer
        open={drawers.setup.open}
        onOpenChange={drawers.onSetupOpenChange}
        setupTab={setupTab}
        onSetupTabChange={onSetupTabChange}
        warehouseMaps={maps.warehouseMaps}
        scannedMaps={scannedMaps}
        selectedWarehouseMapId={maps.selectedWarehouseMapId}
        loadingWarehouseMaps={maps.loadingWarehouseMaps}
        creatingMap={maps.creatingMap}
        deletingWarehouseMap={maps.deletingWarehouseMap}
        onSelectWarehouseMap={(id) => {
          maps.setSelectedWarehouseMapId(id);
          onSelectedDockIdChange(null);
        }}
        onRefreshMaps={() => void maps.loadWarehouseMaps()}
        onCreateMap={maps.handleCreateWarehouseMap}
        onDeleteMapRequest={(map, assetCount) =>
          onDeleteTargetChange({
            kind: "map",
            label: map?.name ?? `Map #${maps.selectedWarehouseMapId}`,
            assetCount,
            onConfirm: () => {
              void maps
                .handleDeleteWarehouseMap()
                .finally(() => onDeleteTargetChange(null));
            },
          })
        }
        sensorRigs={rigs.sensorRigs}
        selectedSensorRigId={rigs.selectedSensorRigId}
        sensorRigHealth={rigs.sensorRigHealth}
        loadingSensorRigs={rigs.loadingSensorRigs}
        savingSensorRig={rigs.savingSensorRig}
        deletingSensorRig={rigs.deletingSensorRig}
        onSelectSensorRig={rigs.setSelectedSensorRigId}
        onRefreshSensorRigs={() => {
          void rigs.loadSensorRigs();
          void rigs.loadSensorRigHealth(rigs.selectedSensorRigId);
        }}
        onCalibrateSensorRig={() => void rigs.handleMarkSensorRigCalibrated()}
        onCreateSensorRig={rigs.handleCreateSensorRig}
        onDeleteSensorRigRequest={(rig) =>
          onDeleteTargetChange({
            kind: "sensor rig",
            label: rig?.name ?? `Sensor rig #${rigs.selectedSensorRigId}`,
            assetCount: 1,
            onConfirm: () => {
              void rigs
                .handleDeleteSensorRig()
                .finally(() => onDeleteTargetChange(null));
            },
          })
        }
        selectedDockId={selectedDockId}
        onSelectedDockIdChange={onSelectedDockIdChange}
        onError={onError}
        missionDefaultsDraft={defaults.missionDefaultsDraft}
        loadingMissionDefaults={defaults.loadingMissionDefaults}
        savingMissionDefaults={defaults.savingMissionDefaults}
        onMissionDefaultsChange={defaults.handleMissionDefaultsDraftChange}
        onSaveMissionDefaults={() => void defaults.handleUpdateMissionDefaults()}
      />
      <WarehouseChecksDrawer
        open={drawers.checks.open}
        onOpenChange={drawers.onChecksOpenChange}
        preflight={preflight.result}
        running={preflight.running}
        error={preflight.error}
        onRunChecks={() => {
          void preflight.runChecks({ missionLoaded: missionLoadedForReadiness });
        }}
      />
      <WarehouseMissionDrawer
        open={drawers.mission.open}
        onOpenChange={drawers.onMissionOpenChange}
        flyMode={flyMode}
        setFlyMode={onFlyModeChange}
        preflightPassed={preflight.passed}
        missionName={missionName}
        missionState={missionState}
        activeFlightId={runtime.activeFlightId}
        lastError={runtime.missionStatus?.mission_lifecycle?.last_error}
        readiness={flightReadiness.data}
        preflight={preflight.result}
        flightReadinessLoading={flightReadiness.isLoading}
        startingScan={scanActions.startingScan}
        startScanDisabled={startScanDisabled}
        startScanTooltip={startScanTooltip}
        onStartScan={() =>
          void scanActions.handleStartWarehouseScan({
            selectedWarehouseMapId: maps.selectedWarehouseMapId,
            selectedSensorRigId: rigs.selectedSensorRigId,
            selectedDockId,
            sensorRigReady: rigs.sensorRigHealth?.ready,
            warehouseMaps: maps.warehouseMaps,
            selectedScannedMap: scanned.selectedScannedMap,
            scannedMaps,
          })
        }
        onPause={() => void scanActions.handleFlightCommand("pause")}
        onAbort={() => void scanActions.handleFlightCommand("abort")}
        onLand={() => void scanActions.handleFlightCommand("land")}
        commandBusy={scanActions.flightCommandBusy}
        warehouseMapId={maps.selectedWarehouseMapId}
        selectedDockId={selectedDockId}
        warehouseName={maps.selectedWarehouseMapName ?? undefined}
        getToken={getToken}
        onExplorationLaunch={scanActions.handleExplorationLaunch}
        onExplorationError={scanActions.handleExplorationError}
        authToken={authToken}
        onError={onError}
        mapPlacementPanelProps={warehouseMapPlacement.panelProps}
        missionStatus={runtime.missionStatus}
        wsConnected={runtime.wsConnected}
        droneConnected={runtime.droneConnected}
        sensorRigId={rigs.selectedSensorRigId}
        setPendingFlightId={runtime.setPendingFlightId}
        onManualMappingPreflightRun={onManualMappingPreflightRun}
        onManualMappingMessage={onManualMappingMessage}
        onScanResultReady={handleScanResultReady}
      />

      <WarehouseDeleteConfirmationDialog
        target={deleteTarget}
        busy={
          maps.deletingWarehouseMap ||
          rigs.deletingSensorRig ||
          scanned.deletingScannedMap
        }
        onClose={() => onDeleteTargetChange(null)}
      />
    </>
  );
}
