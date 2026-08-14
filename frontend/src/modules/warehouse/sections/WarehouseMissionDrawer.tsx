import ExploreRoundedIcon from "@mui/icons-material/ExploreRounded";
import { TaskPreflightCommandsDrawer } from "../../mission-workflow";
import type { PreflightRunResponse, MissionLifecycleState } from "../../mission-runtime";
import type { Dispatch, SetStateAction, ComponentProps } from "react";
import {
  WarehouseFlyDrawerContent,
  type WarehouseFlyMode,
} from "../components/WarehouseFlyDrawerContent";

import type { WarehouseFlightReadiness } from "../api/warehouseFlightApi";
import type { WarehouseGoPreflight } from "../api/warehousePreflightApi";
import type { WarehouseMissionLaunchResponse } from "../types/missions";
import type { WarehouseMissionStatus } from "../warehousePageSupport";

type MapPlacementPanelProps = ComponentProps<
  typeof WarehouseFlyDrawerContent
>["productScanProps"]["mapPlacement"];

type WarehouseMissionDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  flyMode: WarehouseFlyMode;
  setFlyMode: Dispatch<SetStateAction<WarehouseFlyMode>>;
  preflightPassed: boolean;
  missionName: string;
  missionState: MissionLifecycleState | string;
  activeFlightId: string | null;
  lastError: string | null | undefined;
  readiness: WarehouseFlightReadiness | undefined;
  preflight: WarehouseGoPreflight | null;
  flightReadinessLoading: boolean;
  startingScan: boolean;
  startScanDisabled: boolean;
  startScanTooltip: string;
  onStartScan: () => void;
  onPause: () => void;
  onAbort: () => void;
  onLand: () => void;
  commandBusy: boolean;
  warehouseMapId: number | null;
  selectedDockId: number | null;
  warehouseName: string | undefined;
  getToken: () => string | null;
  onExplorationLaunch: (launch: WarehouseMissionLaunchResponse) => void;
  onExplorationError: (message: string, error?: unknown) => void;
  authToken: string | null;
  onError: (message: string) => void;
  mapPlacementPanelProps: MapPlacementPanelProps;
  missionStatus: WarehouseMissionStatus | null;
  wsConnected: boolean;
  droneConnected: boolean;
  sensorRigId: number | null;
  setPendingFlightId: (flightId: string | null) => void;
  onManualMappingPreflightRun: (preflight: PreflightRunResponse | null) => void;
  onManualMappingMessage: (message: string) => void;
  onScanResultReady: (jobId: number) => void;
};

export function WarehouseMissionDrawer({
  open,
  onOpenChange,
  flyMode,
  setFlyMode,
  preflightPassed,
  missionName,
  missionState,
  activeFlightId,
  lastError,
  readiness,
  preflight,
  flightReadinessLoading,
  startingScan,
  startScanDisabled,
  startScanTooltip,
  onStartScan,
  onPause,
  onAbort,
  onLand,
  commandBusy,
  warehouseMapId,
  selectedDockId,
  warehouseName,
  getToken,
  onExplorationLaunch,
  onExplorationError,
  authToken,
  onError,
  mapPlacementPanelProps,
  missionStatus,
  wsConnected,
  droneConnected,
  sensorRigId,
  setPendingFlightId,
  onManualMappingPreflightRun,
  onManualMappingMessage,
  onScanResultReady,
}: WarehouseMissionDrawerProps) {
  return (
    <TaskPreflightCommandsDrawer
      open={open}
      onOpenChange={onOpenChange}
      title="Warehouse Fly"
      subtitle="Automated scan, product scan, and manual mapping"
      tabLabel="FLY"
      tabIcon={<ExploreRoundedIcon fontSize="small" />}
      edgeTabIndex={2}
      edgeTabCount={3}
      paperSx={{ width: { xs: "min(100vw, 520px)", sm: 540, md: 560 } }}
    >
      <WarehouseFlyDrawerContent
        flyMode={flyMode}
        setFlyMode={setFlyMode}
        preflightPassed={preflightPassed}
        missionStatusProps={{
          missionName,
          missionState,
          activeFlightId,
          lastError,
        }}
        readinessProps={{
          readiness,
          preflight,
          loading: flightReadinessLoading,
          starting: startingScan,
          startDisabled: startScanDisabled,
          startDisabledReason: startScanTooltip,
          onStart: onStartScan,
          onPause,
          onAbort,
          onLand,
          commandBusy,
          showControls: missionState === "running",
        }}
        explorationProps={{
          embedded: true,
          warehouseMapId,
          selectedDockId,
          warehouseName,
          warehousePreflightPassed: preflightPassed,
          getToken,
          onLaunch: onExplorationLaunch,
          onError: onExplorationError,
        }}
        productScanProps={{
          warehouseMapId,
          token: authToken,
          onError,
          mapPlacement: mapPlacementPanelProps,
        }}
        manualMappingProps={{
          embedded: true,
          activeFlightId,
          missionStatus,
          wsConnected,
          droneConnected,
          warehouseMapId,
          sensorRigId,
          dockId: selectedDockId,
          warehousePreflightPassed: preflightPassed,
          setPendingFlightId,
          onPreflightRun: onManualMappingPreflightRun,
          onMessage: onManualMappingMessage,
          onError,
          onScanResultReady,
        }}
      />
    </TaskPreflightCommandsDrawer>
  );
}
