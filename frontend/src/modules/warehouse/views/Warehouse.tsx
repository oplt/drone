import { useEffect } from "react";
import type { PreflightRunResponse } from "../../mission-runtime";
import { useErrors } from "../../../shared/hooks/useErrors";
import { useNotice } from "../../../shared/ui/NoticeContext";
import { useRunWarehousePreflight } from "../hooks/useRunWarehousePreflight";
import { useWarehouseFlightReadiness } from "../hooks/useWarehouseFlightReadiness";
import { useWarehouseMapPlacement } from "../hooks/useWarehouseMapPlacement";
import { useWarehouseMissionDefaults } from "../hooks/useWarehouseMissionDefaults";
import { useWarehouseMissionRuntimeController } from "../hooks/useWarehouseMissionRuntimeController";
import { useWarehouseMaps } from "../hooks/useWarehouseMaps";
import { useWarehousePageUiState } from "../hooks/useWarehousePageUiState";
import { useWarehouseResourceQueries } from "../hooks/useWarehouseResourceQueries";
import { useWarehouseScannedMapActions } from "../hooks/useWarehouseScannedMapActions";
import { useWarehouseScanActions } from "../hooks/useWarehouseScanActions";
import { useWarehouseSelectionPersistence } from "../hooks/useWarehouseSelectionPersistence";
import { useWarehouseSensorRigs } from "../hooks/useWarehouseSensorRigs";
import { useWarehouseViewerSession } from "../hooks/useWarehouseViewerSession";
import { WarehousePageDrawersSection } from "../sections/WarehousePageDrawersSection";
import { WarehousePageMainSection } from "../sections/WarehousePageMainSection";

export default function WarehousePage() {
  const ui = useWarehousePageUiState();
  const { notify } = useNotice();
  const { errors, addError, clearErrors, dismissError } = useErrors();
  const {
    localStorageKey,
    setSelectedDockId,
    setSetupTab,
    selectedDockId,
    setupTab,
    mapDetailTab,
    setMapDetailTab,
    setDeleteTarget,
  } = ui;

  const maps = useWarehouseMaps({
    addError,
    notify,
    onMapDeleted: () => setSelectedDockId(null),
  });
  const rigs = useWarehouseSensorRigs({ addError, notify });
  const defaults = useWarehouseMissionDefaults({ addError, notify });
  const resourceQueries = useWarehouseResourceQueries(maps.selectedWarehouseMapId);
  const scannedMaps = resourceQueries.scannedMaps.data ?? [];
  const scanned = useWarehouseScannedMapActions({
    scannedMaps,
    refetchScannedMaps: resourceQueries.scannedMaps.refetch,
    addError,
    notify,
  });

  useWarehouseSelectionPersistence({
    localStorageKey,
    setSelectedWarehouseMapId: maps.setSelectedWarehouseMapId,
    setSelectedSensorRigId: rigs.setSelectedSensorRigId,
    setSelectedDockId,
    setSetupTab,
    selection: {
      selectedWarehouseMapId: maps.selectedWarehouseMapId,
      selectedSensorRigId: rigs.selectedSensorRigId,
      selectedDockId,
      setupTab,
    },
  });

  const preflight = useRunWarehousePreflight(ui.authToken);
  const flightReadiness = useWarehouseFlightReadiness(ui.authToken, {
    missionLoaded:
      maps.selectedWarehouseMapId != null && rigs.selectedSensorRigId != null,
    enabled:
      Boolean(ui.authToken) &&
      (ui.drawers.checks.open || ui.drawers.mission.open || preflight.running),
    preflightRunning: preflight.running,
  });
  const warehouseMapPlacement = useWarehouseMapPlacement({
    warehouseMapId: maps.selectedWarehouseMapId,
    token: ui.authToken,
    onError: addError,
  });

  useEffect(() => {
    if (mapDetailTab !== "coordinateSetup") {
      warehouseMapPlacement.panelProps.setPickMode(false);
    }
  }, [mapDetailTab, warehouseMapPlacement.panelProps]);

  useEffect(() => {
    if (maps.selectedWarehouseMapId == null) setMapDetailTab("layers");
  }, [maps.selectedWarehouseMapId, setMapDetailTab]);

  const runtime = useWarehouseMissionRuntimeController({
    apiBase: ui.apiBase,
    onError: addError,
  });
  const scanActions = useWarehouseScanActions({
    addError,
    notify,
    setPendingFlightId: runtime.setPendingFlightId,
    refetchWarehouseFlightReadiness: flightReadiness.refetch,
    loadScannedMaps: () => scanned.loadScannedMaps(),
  });
  const viewer = useWarehouseViewerSession({
    runtime,
    scanned,
    selectedWarehouseMapId: maps.selectedWarehouseMapId,
    preflightPassed: preflight.passed,
    authToken: ui.authToken,
    viewerSectionRef: ui.viewerSectionRef,
    previousMissionStateRef: ui.previousMissionStateRef,
    notify,
    startingScan: scanActions.startingScan,
    selectedSensorRigId: rigs.selectedSensorRigId,
    sensorRigReady: rigs.sensorRigHealth?.ready,
    perceptionReady: rigs.sensorRigHealth?.perception?.ready,
  });

  return (
    <>
      <WarehousePageMainSection
        systemStatusItems={viewer.systemStatusItems}
        maps={maps}
        rigs={rigs}
        selectedDockId={selectedDockId}
        preflight={preflight.result}
        runtime={runtime}
        errors={errors}
        onDismissError={dismissError}
        onClearErrors={clearErrors}
        mobileLayout={ui.mobileLayout}
        mobileTab={ui.mobileTab}
        onMobileTabChange={ui.setMobileTab}
        apiBase={ui.apiBase}
        authToken={ui.authToken}
        viewerSectionRef={ui.viewerSectionRef}
        viewer={viewer}
        scanned={scanned}
        scannedMapsLoading={resourceQueries.scannedMaps.isLoading}
        drawers={ui.drawers}
        warehouseMapPlacement={warehouseMapPlacement}
        mapDetailTab={mapDetailTab}
        onMapDetailTabChange={setMapDetailTab}
        onError={addError}
        onOpenSetup={() => ui.drawers.onSetupOpenChange(true)}
        onOpenChecks={() => ui.drawers.onChecksOpenChange(true)}
        onOpenMission={() => ui.drawers.onMissionOpenChange(true)}
        setDeleteTarget={setDeleteTarget}
      />
      <WarehousePageDrawersSection
        drawers={ui.drawers}
        setupTab={setupTab}
        onSetupTabChange={setSetupTab}
        maps={maps}
        scannedMaps={scannedMaps}
        rigs={rigs}
        selectedDockId={selectedDockId}
        onSelectedDockIdChange={setSelectedDockId}
        onError={addError}
        defaults={defaults}
        preflight={preflight}
        missionLoadedForReadiness={
          maps.selectedWarehouseMapId != null && rigs.selectedSensorRigId != null
        }
        flyMode={ui.flyMode}
        onFlyModeChange={ui.setFlyMode}
        viewer={viewer}
        runtime={runtime}
        flightReadiness={flightReadiness}
        scanActions={scanActions}
        warehouseMapPlacement={warehouseMapPlacement}
        authToken={ui.authToken}
        scanned={scanned}
        deleteTarget={ui.deleteTarget}
        onDeleteTargetChange={setDeleteTarget}
        onManualMappingMessage={(message) => notify(message, "success")}
        onManualMappingPreflightRun={(run: PreflightRunResponse | null) => {
          if (run) notify(`Keyboard preflight ${run.overall_status}.`, "info");
        }}
      />
    </>
  );
}
