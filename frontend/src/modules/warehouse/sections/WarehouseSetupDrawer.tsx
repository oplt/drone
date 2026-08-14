import { CircularProgress, Stack, Tab, Tabs } from "@mui/material";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";
import { TaskPreflightCommandsDrawer } from "../../mission-workflow";
import { getToken } from "../../session";
import { WarehouseDockPanel } from "../components/WarehouseDockPanel";
import { WarehouseDrawerSection } from "../components/WarehouseDrawerSection";
import { WarehouseMapSetupPanel } from "../components/WarehouseMapSetupPanel";
import { WarehouseMissionDefaultsPanel } from "../components/WarehouseMissionDefaultsPanel";
import { WarehouseSensorRigSetupPanel } from "../components/WarehouseSensorRigSetupPanel";
import type { WarehouseMapOut, WarehouseSensorRig, WarehouseSensorRigHealth } from "../types";
import type { WarehouseScannedMapResponse } from "../types/missions";
import type { CreateMapForm, SensorRigForm } from "../warehousePageSupport";
import type { WarehouseMissionDefaultsDraft, WarehouseMissionDefaultsKey } from "../warehouseMissionDefaults";

type WarehouseSetupDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  setupTab: "map" | "rig" | "dock" | "defaults";
  onSetupTabChange: (tab: "map" | "rig" | "dock" | "defaults") => void;
  warehouseMaps: WarehouseMapOut[];
  scannedMaps: WarehouseScannedMapResponse[];
  selectedWarehouseMapId: number | null;
  loadingWarehouseMaps: boolean;
  creatingMap: boolean;
  deletingWarehouseMap: boolean;
  onSelectWarehouseMap: (id: number | null) => void;
  onRefreshMaps: () => void;
  onCreateMap: (form: CreateMapForm) => Promise<boolean>;
  onDeleteMapRequest: (
    map: WarehouseMapOut | undefined,
    assetCount: number,
  ) => void;
  sensorRigs: WarehouseSensorRig[];
  selectedSensorRigId: number | null;
  sensorRigHealth: WarehouseSensorRigHealth | null;
  loadingSensorRigs: boolean;
  savingSensorRig: boolean;
  deletingSensorRig: boolean;
  onSelectSensorRig: (id: number | null) => void;
  onRefreshSensorRigs: () => void;
  onCalibrateSensorRig: () => void;
  onCreateSensorRig: (form: SensorRigForm) => Promise<boolean>;
  onDeleteSensorRigRequest: (rig: WarehouseSensorRig | undefined) => void;
  selectedDockId: number | null;
  onSelectedDockIdChange: (id: number | null) => void;
  onError: (message: string) => void;
  missionDefaultsDraft: WarehouseMissionDefaultsDraft | null;
  loadingMissionDefaults: boolean;
  savingMissionDefaults: boolean;
  onMissionDefaultsChange: (key: WarehouseMissionDefaultsKey, value: string) => void;
  onSaveMissionDefaults: () => void;
};

export function WarehouseSetupDrawer({
  open,
  onOpenChange,
  setupTab,
  onSetupTabChange,
  warehouseMaps,
  scannedMaps,
  selectedWarehouseMapId,
  loadingWarehouseMaps,
  creatingMap,
  deletingWarehouseMap,
  onSelectWarehouseMap,
  onRefreshMaps,
  onCreateMap,
  onDeleteMapRequest,
  sensorRigs,
  selectedSensorRigId,
  sensorRigHealth,
  loadingSensorRigs,
  savingSensorRig,
  deletingSensorRig,
  onSelectSensorRig,
  onRefreshSensorRigs,
  onCalibrateSensorRig,
  onCreateSensorRig,
  onDeleteSensorRigRequest,
  selectedDockId,
  onSelectedDockIdChange,
  onError,
  missionDefaultsDraft,
  loadingMissionDefaults,
  savingMissionDefaults,
  onMissionDefaultsChange,
  onSaveMissionDefaults,
}: WarehouseSetupDrawerProps) {
  return (
    <TaskPreflightCommandsDrawer
      open={open}
      onOpenChange={onOpenChange}
      title="Warehouse Setup"
      subtitle="Map, sensor rig, dock, and scan defaults"
      tabLabel="SETUP"
      tabIcon={<TuneRoundedIcon fontSize="small" />}
      edgeTabIndex={0}
      edgeTabCount={3}
      paperSx={{
        width: {
          xs: "min(100vw, 560px)",
          sm: 680,
          md: 760,
          lg: 840,
        },
        maxWidth: "100vw",
      }}
    >
      <Stack spacing={2}>
        <Tabs
          value={setupTab}
          onChange={(_, value: "map" | "rig" | "dock" | "defaults") =>
            onSetupTabChange(value)
          }
          variant="scrollable"
          allowScrollButtonsMobile
        >
          <Tab value="map" label="Map" />
          <Tab value="rig" label="Sensor Rig" />
          <Tab value="dock" label="Dock" />
          <Tab value="defaults" label="Defaults" />
        </Tabs>
        {setupTab === "map" && (
          <WarehouseDrawerSection
            title="Warehouse Map"
            info="Select the warehouse footprint. The drone scans using local metric coordinates — no GPS required. Origin (0, 0) is the takeoff position."
            action={loadingWarehouseMaps ? <CircularProgress size={16} /> : null}
          >
            <WarehouseMapSetupPanel
              maps={warehouseMaps}
              scannedMaps={scannedMaps}
              selectedId={selectedWarehouseMapId}
              loading={loadingWarehouseMaps}
              creating={creatingMap}
              deleting={deletingWarehouseMap}
              onSelect={onSelectWarehouseMap}
              onRefresh={onRefreshMaps}
              onCreate={onCreateMap}
              onDelete={onDeleteMapRequest}
              getToken={getToken}
            />
          </WarehouseDrawerSection>
        )}
        {setupTab === "rig" && (
          <WarehouseDrawerSection
            title="Sensor Rig"
            info="Register calibrated hardware and map sim or real-device ROS source topics to stable /warehouse/contract/* topics."
            action={loadingSensorRigs ? <CircularProgress size={16} /> : null}
          >
            <WarehouseSensorRigSetupPanel
              rigs={sensorRigs}
              selectedId={selectedSensorRigId}
              health={sensorRigHealth}
              loading={loadingSensorRigs}
              saving={savingSensorRig}
              deleting={deletingSensorRig}
              onSelect={onSelectSensorRig}
              onRefresh={onRefreshSensorRigs}
              onCalibrate={onCalibrateSensorRig}
              onCreate={onCreateSensorRig}
              onDelete={onDeleteSensorRigRequest}
            />
          </WarehouseDrawerSection>
        )}
        {setupTab === "dock" && (
          <WarehouseDrawerSection
            title="Dock Station"
            info="Optional local-frame anchor for takeoff, return, and exploration missions."
          >
            <WarehouseDockPanel
              embedded
              warehouseMapId={selectedWarehouseMapId}
              selectedDockId={selectedDockId}
              onSelectedDockIdChange={onSelectedDockIdChange}
              getToken={getToken}
              onError={onError}
            />
          </WarehouseDrawerSection>
        )}
        {setupTab === "defaults" && (
          <WarehouseDrawerSection
            title="Default Flight Parameters"
            info="Controls aisle spacing, scan layers, ceiling clearance, and rack-facing view behavior for automated warehouse scan missions."
            action={loadingMissionDefaults ? <CircularProgress size={16} /> : null}
          >
            <WarehouseMissionDefaultsPanel
              draft={missionDefaultsDraft}
              saving={savingMissionDefaults}
              successMessage={null}
              onChange={onMissionDefaultsChange}
              onSave={onSaveMissionDefaults}
            />
          </WarehouseDrawerSection>
        )}
      </Stack>
    </TaskPreflightCommandsDrawer>
  );
}
