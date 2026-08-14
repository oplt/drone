import { useCallback, useState } from "react";
import { getToken } from "../../session";
import {
  createWarehouseSensorRig,
  deleteWarehouseSensorRig,
  updateWarehouseSensorRigCalibration,
} from "../api/warehouseMapsApi";
import { DEFAULT_WAREHOUSE_SENSOR_EXTRINSICS } from "../types";
import type { WarehouseSensorRig } from "../types";
import type { SensorRigForm } from "../warehousePageSupport";
import { toMessage } from "../warehousePageSupport";

type UseWarehouseSensorRigMutationsOptions = {
  addError: (message: string) => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
  sensorRigs: WarehouseSensorRig[];
  selectedSensorRigId: number | null;
  setSelectedSensorRigId: (id: number | null) => void;
  setSensorRigHealth: (health: null) => void;
  loadSensorRigs: () => Promise<void>;
  loadSensorRigHealth: (sensorRigId: number | null) => Promise<void>;
};

export function useWarehouseSensorRigMutations({
  addError,
  notify,
  sensorRigs,
  selectedSensorRigId,
  setSelectedSensorRigId,
  setSensorRigHealth,
  loadSensorRigs,
  loadSensorRigHealth,
}: UseWarehouseSensorRigMutationsOptions) {
  const [savingSensorRig, setSavingSensorRig] = useState(false);
  const [deletingSensorRig, setDeletingSensorRig] = useState(false);

  const handleCreateSensorRig = useCallback(
    async (sensorRigForm: SensorRigForm) => {
      const token = getToken();
      if (!token) return false;
      const name = sensorRigForm.name.trim();
      const cameraModel = sensorRigForm.camera_model.trim();
      if (!name || !cameraModel) {
        addError(name ? "Camera model is required." : "Sensor rig name is required.");
        return false;
      }
      const baselineRaw = sensorRigForm.stereo_baseline_m.trim();
      const baseline = baselineRaw ? Number(baselineRaw) : null;
      if (baselineRaw && (!Number.isFinite(baseline) || Number(baseline) <= 0)) {
        addError("Stereo baseline must be a positive number.");
        return false;
      }
      setSavingSensorRig(true);
      try {
        const created = await createWarehouseSensorRig(
          {
            name,
            camera_model: cameraModel,
            stereo_baseline_m: baseline,
            intrinsics_url: sensorRigForm.intrinsics_url.trim() || null,
            extrinsics_url: sensorRigForm.extrinsics_url.trim() || null,
            extrinsics_json: DEFAULT_WAREHOUSE_SENSOR_EXTRINSICS,
            firmware_version: sensorRigForm.firmware_version.trim() || null,
            imu_transform_json: {},
          },
          token,
        );
        await loadSensorRigs();
        setSelectedSensorRigId(created.id);
        await loadSensorRigHealth(created.id);
        return true;
      } catch (error) {
        addError(`Could not create sensor rig: ${toMessage(error)}`);
        return false;
      } finally {
        setSavingSensorRig(false);
      }
    },
    [
      addError,
      loadSensorRigHealth,
      loadSensorRigs,
      setSelectedSensorRigId,
    ],
  );
  const handleDeleteSensorRig = useCallback(async () => {
    if (selectedSensorRigId == null) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete sensor rigs.");
      return;
    }
    const rig = sensorRigs.find((item) => item.id === selectedSensorRigId);
    const label = rig?.name ?? `Sensor rig #${selectedSensorRigId}`;

    setDeletingSensorRig(true);
    try {
      await deleteWarehouseSensorRig(selectedSensorRigId, token);
      setSelectedSensorRigId(null);
      setSensorRigHealth(null);
      await loadSensorRigs();
      notify(`Deleted sensor rig "${label}".`, "success");
    } catch (error) {
      addError(`Could not delete sensor rig: ${toMessage(error)}`);
    } finally {
      setDeletingSensorRig(false);
    }
  }, [
    addError,
    loadSensorRigs,
    notify,
    selectedSensorRigId,
    sensorRigs,
    setSelectedSensorRigId,
    setSensorRigHealth,
  ]);
  const handleMarkSensorRigCalibrated = useCallback(async () => {
    const token = getToken();
    if (!token || selectedSensorRigId == null) return;
    const rig = sensorRigs.find((item) => item.id === selectedSensorRigId);
    if (!rig) return;
    setSavingSensorRig(true);
    try {
      await updateWarehouseSensorRigCalibration(
        selectedSensorRigId,
        {
          calibration_status: "valid",
          intrinsics_url: rig.intrinsics_url,
          extrinsics_url: rig.extrinsics_url,
          extrinsics_json: rig.extrinsics_json,
          imu_transform_json: rig.imu_transform_json,
          calibration_meta: {
            ...rig.calibration_meta,
            source: "operator_update",
            updated_at: new Date().toISOString(),
          },
        },
        token,
      );
      await loadSensorRigs();
      await loadSensorRigHealth(selectedSensorRigId);
      notify(`Sensor rig "${rig.name}" calibration saved.`, "success");
    } catch (error) {
      addError(`Could not update sensor rig calibration: ${toMessage(error)}`);
    } finally {
      setSavingSensorRig(false);
    }
  }, [
    addError,
    loadSensorRigHealth,
    loadSensorRigs,
    notify,
    selectedSensorRigId,
    sensorRigs,
  ]);

  return {
    savingSensorRig,
    deletingSensorRig,
    handleCreateSensorRig,
    handleDeleteSensorRig,
    handleMarkSensorRigCalibrated,
  };
}
