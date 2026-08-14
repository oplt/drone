import { useEffect } from "react";
import type { WarehousePageState } from "../warehousePageState";

type PersistedSelection = {
  selectedWarehouseMapId: number | null;
  selectedSensorRigId: number | null;
  selectedDockId: number | null;
  setupTab: WarehousePageState["setupTab"];
};

type UseWarehouseSelectionPersistenceOptions = {
  localStorageKey: string;
  setSelectedWarehouseMapId: (value: number | null) => void;
  setSelectedSensorRigId: (value: number | null) => void;
  setSelectedDockId: (value: number | null) => void;
  setSetupTab: (tab: WarehousePageState["setupTab"]) => void;
  selection: PersistedSelection;
};

export function useWarehouseSelectionPersistence({
  localStorageKey,
  setSelectedWarehouseMapId,
  setSelectedSensorRigId,
  setSelectedDockId,
  setSetupTab,
  selection,
}: UseWarehouseSelectionPersistenceOptions) {
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(localStorageKey);
      if (!raw) return;
      const saved = JSON.parse(raw) as {
        selectedWarehouseMapId?: number | null;
        selectedSensorRigId?: number | null;
        selectedDockId?: number | null;
        setupTab?: WarehousePageState["setupTab"];
      };
      if (typeof saved.selectedWarehouseMapId === "number") {
        setSelectedWarehouseMapId(saved.selectedWarehouseMapId);
      }
      if (typeof saved.selectedSensorRigId === "number") {
        setSelectedSensorRigId(saved.selectedSensorRigId);
      }
      if (typeof saved.selectedDockId === "number") {
        setSelectedDockId(saved.selectedDockId);
      }
      if (saved.setupTab) {
        setSetupTab(saved.setupTab);
      }
    } catch {
      window.localStorage.removeItem(localStorageKey);
    }
  }, [
    localStorageKey,
    setSelectedDockId,
    setSelectedSensorRigId,
    setSelectedWarehouseMapId,
    setSetupTab,
  ]);

  useEffect(() => {
    try {
      window.localStorage.setItem(localStorageKey, JSON.stringify(selection));
    } catch {
      // Local storage is a convenience only.
    }
  }, [localStorageKey, selection]);
}
