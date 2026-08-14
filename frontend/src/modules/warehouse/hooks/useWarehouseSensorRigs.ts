import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "../../session";
import {
  fetchWarehouseSensorRigHealth,
  listWarehouseSensorRigs,
} from "../api/warehouseMapsApi";
import type { WarehouseSensorRig, WarehouseSensorRigHealth } from "../types";
import { toMessage } from "../warehousePageSupport";
import { useWarehouseSensorRigMutations } from "./useWarehouseSensorRigMutations";

type UseWarehouseSensorRigsOptions = {
  addError: (message: string) => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
};

export function useWarehouseSensorRigs({
  addError,
  notify,
}: UseWarehouseSensorRigsOptions) {
  const [sensorRigs, setSensorRigs] = useState<WarehouseSensorRig[]>([]);
  const [selectedSensorRigId, setSelectedSensorRigId] = useState<number | null>(
    null,
  );
  const [sensorRigHealth, setSensorRigHealth] =
    useState<WarehouseSensorRigHealth | null>(null);
  const [loadingSensorRigs, setLoadingSensorRigs] = useState(false);
  const sensorRigHealthRequestRef = useRef(0);

  const loadSensorRigs = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoadingSensorRigs(true);
    try {
      const rigs = await listWarehouseSensorRigs(token);
      setSensorRigs(rigs);
      setSelectedSensorRigId((current) => {
        if (current != null && rigs.some((rig) => rig.id === current)) return current;
        return rigs[0]?.id ?? null;
      });
    } catch (error) {
      addError(`Sensor rigs could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingSensorRigs(false);
    }
  }, [addError]);

  const loadSensorRigHealth = useCallback(
    async (sensorRigId: number | null) => {
      const token = getToken();
      const requestId = sensorRigHealthRequestRef.current + 1;
      sensorRigHealthRequestRef.current = requestId;
      if (!token || sensorRigId == null) {
        setSensorRigHealth(null);
        return;
      }
      try {
        const health = await fetchWarehouseSensorRigHealth(sensorRigId, token);
        if (sensorRigHealthRequestRef.current !== requestId) return;
        setSensorRigHealth(health);
      } catch (error) {
        if (sensorRigHealthRequestRef.current !== requestId) return;
        setSensorRigHealth(null);
        addError(`Sensor rig health could not be loaded: ${toMessage(error)}`);
      }
    },
    [addError],
  );

  useEffect(() => {
    void loadSensorRigs();
  }, [loadSensorRigs]);

  useEffect(() => {
    void loadSensorRigHealth(selectedSensorRigId);
  }, [loadSensorRigHealth, selectedSensorRigId]);

  const mutations = useWarehouseSensorRigMutations({
    addError,
    notify,
    sensorRigs,
    selectedSensorRigId,
    setSelectedSensorRigId,
    setSensorRigHealth,
    loadSensorRigs,
    loadSensorRigHealth,
  });

  return {
    sensorRigs,
    selectedSensorRigId,
    setSelectedSensorRigId,
    sensorRigHealth,
    loadingSensorRigs,
    loadSensorRigs,
    loadSensorRigHealth,
    ...mutations,
  };
}
