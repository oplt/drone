import { useCallback, useState } from "react";
import { getToken } from "../../session";
import { sendWarehouseFlightCommand } from "../api/warehouseFlightApi";
import { startWarehouseScan } from "../api/warehouseMissionsApi";
import type { WarehouseMapOut } from "../types";
import type {
  WarehouseMissionLaunchResponse,
  WarehouseScannedMapResponse,
} from "../types/missions";
import {
  getWarehouseMapId,
} from "../scannedMapSelectors";
import {
  getWarehouseStartMessage,
  getWarehouseStartPreflight,
  toMessage,
} from "../warehousePageSupport";

type UseWarehouseScanActionsOptions = {
  addError: (message: string) => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
  setPendingFlightId: (flightId: string) => void;
  refetchWarehouseFlightReadiness: () => void;
  loadScannedMaps: () => Promise<unknown>;
};

type StartScanInput = {
  selectedWarehouseMapId: number | null;
  selectedSensorRigId: number | null;
  selectedDockId: number | null;
  sensorRigReady: boolean | undefined;
  warehouseMaps: WarehouseMapOut[];
  selectedScannedMap: WarehouseScannedMapResponse | null;
  scannedMaps: WarehouseScannedMapResponse[];
};

export function useWarehouseScanActions({
  addError,
  notify,
  setPendingFlightId,
  refetchWarehouseFlightReadiness,
  loadScannedMaps,
}: UseWarehouseScanActionsOptions) {
  const [startingScan, setStartingScan] = useState(false);
  const [flightCommandBusy, setFlightCommandBusy] = useState(false);

  const handleStartWarehouseScan = useCallback(
    async (input: StartScanInput) => {
      const token = getToken();
      if (!token) {
        addError("You must be authenticated to start a warehouse scan.");
        return;
      }
      if (!input.selectedWarehouseMapId) {
        addError("Select a warehouse map to define the scan area.");
        return;
      }
      if (input.selectedSensorRigId == null || input.sensorRigReady !== true) {
        addError(
          "Select a calibrated warehouse sensor rig before starting the scan.",
        );
        return;
      }

      const warehouseMap = input.warehouseMaps.find(
        (m) => m.id === input.selectedWarehouseMapId,
      );

      setStartingScan(true);
      try {
        const launch = await startWarehouseScan(
          {
            warehouse_map_id: input.selectedWarehouseMapId,
            mission_name: `Warehouse Scan${warehouseMap ? ` - ${warehouseMap.name}` : ""}`,
            sensor_rig_id: input.selectedSensorRigId,
            dock_id: input.selectedDockId,
            reference_mapping_job_id:
              input.selectedScannedMap?.job_id ??
              input.scannedMaps.find(
                (m) => getWarehouseMapId(m) === input.selectedWarehouseMapId,
              )?.job_id,
          },
          token,
        );

        setPendingFlightId(launch.mission.flight_id);
        void refetchWarehouseFlightReadiness();
        const launchWarehouseName = launch.warehouse_name.trim() || "Warehouse";
        notify(
          `Started ${launch.mission.mission_name} in ${launchWarehouseName}. Preflight ${launch.preflight.overall_status}.`,
          "success",
        );
        void loadScannedMaps();
      } catch (error) {
        const preflight = getWarehouseStartPreflight(error);
        if (preflight) addError(`Latest preflight: ${preflight.overall_status}.`);
        addError(
          `Warehouse scan could not be started: ${getWarehouseStartMessage(error)}`,
        );
      } finally {
        setStartingScan(false);
      }
    },
    [
      addError,
      loadScannedMaps,
      notify,
      refetchWarehouseFlightReadiness,
      setPendingFlightId,
    ],
  );

  const handleFlightCommand = useCallback(
    async (command: "pause" | "abort" | "land") => {
      const token = getToken();
      if (!token) {
        addError("You must be authenticated to send flight commands.");
        return;
      }
      setFlightCommandBusy(true);
      try {
        const result = await sendWarehouseFlightCommand(command, token);
        void refetchWarehouseFlightReadiness();
        if (!result.accepted) {
          addError(result.message || `Flight ${command} command failed.`);
        }
      } catch (error) {
        addError(toMessage(error));
      } finally {
        setFlightCommandBusy(false);
      }
    },
    [addError, refetchWarehouseFlightReadiness],
  );

  const handleExplorationLaunch = useCallback(
    (launch: WarehouseMissionLaunchResponse) => {
      setPendingFlightId(launch.mission.flight_id);
      const launchWarehouseName = launch.warehouse_name.trim() || "Warehouse";
      notify(
        `Started ${launch.mission.mission_name} in ${launchWarehouseName}. Preflight ${launch.preflight.overall_status}.`,
        "success",
      );
    },
    [notify, setPendingFlightId],
  );

  const handleExplorationError = useCallback(
    (message: string, error?: unknown) => {
      const preflight = getWarehouseStartPreflight(error);
      if (preflight) addError(`Latest preflight: ${preflight.overall_status}.`);
      addError(`${message}${error ? ` ${toMessage(error)}` : ""}`);
    },
    [addError],
  );

  return {
    startingScan,
    flightCommandBusy,
    handleStartWarehouseScan,
    handleFlightCommand,
    handleExplorationLaunch,
    handleExplorationError,
  };
}
