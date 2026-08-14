import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../shared/api/apiError";
import { getToken } from "../../session";
import {
  createWarehouseMap,
  deleteWarehouseMap,
  listWarehouseMaps,
} from "../api/warehouseMapsApi";
import type { WarehouseMapOut } from "../types";
import type { CreateMapForm } from "../warehousePageSupport";
import { toMessage } from "../warehousePageSupport";

type UseWarehouseMapsOptions = {
  addError: (message: string) => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
  onMapDeleted: () => void;
};

export function useWarehouseMaps({
  addError,
  notify,
  onMapDeleted,
}: UseWarehouseMapsOptions) {
  const [warehouseMaps, setWarehouseMaps] = useState<WarehouseMapOut[]>([]);
  const [loadingWarehouseMaps, setLoadingWarehouseMaps] = useState(false);
  const [selectedWarehouseMapId, setSelectedWarehouseMapId] = useState<number | null>(
    null,
  );
  const [creatingMap, setCreatingMap] = useState(false);
  const [deletingWarehouseMap, setDeletingWarehouseMap] = useState(false);

  const loadWarehouseMaps = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoadingWarehouseMaps(true);
    try {
      const maps = await listWarehouseMaps(token);
      setWarehouseMaps(maps);
      setSelectedWarehouseMapId((current) => {
        if (current != null && maps.some((m) => m.id === current)) return current;
        return maps[0]?.id ?? null;
      });
    } catch (error) {
      addError(`Warehouse maps could not be loaded: ${toMessage(error)}`);
    } finally {
      setLoadingWarehouseMaps(false);
    }
  }, [addError]);

  useEffect(() => {
    void loadWarehouseMaps();
  }, [loadWarehouseMaps]);

  const handleCreateWarehouseMap = useCallback(
    async (createMapForm: CreateMapForm) => {
      const token = getToken();
      if (!token) return false;
      const name = createMapForm.name.trim();
      if (!name) {
        addError("Map name is required.");
        return false;
      }
      const width = Number(createMapForm.width_m);
      const length = Number(createMapForm.length_m);
      if (!Number.isFinite(width) || width <= 0) {
        addError("Width must be a positive number.");
        return false;
      }
      if (!Number.isFinite(length) || length <= 0) {
        addError("Length must be a positive number.");
        return false;
      }
      setCreatingMap(true);
      try {
        const created = await createWarehouseMap(
          { name, width_m: width, length_m: length },
          token,
        );
        await loadWarehouseMaps();
        setSelectedWarehouseMapId(created.id);
        notify(`Warehouse map "${created.name}" saved.`, "success");
        return true;
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          addError(
            "Could not create warehouse map: insufficient permissions. Check your account role in the sidebar (needs operator/pilot or higher). Restart the backend if this persists after a recent update.",
          );
        } else {
          addError(`Could not create warehouse map: ${toMessage(error)}`);
        }
        return false;
      } finally {
        setCreatingMap(false);
      }
    },
    [addError, loadWarehouseMaps, notify],
  );

  const handleDeleteWarehouseMap = useCallback(async () => {
    if (selectedWarehouseMapId == null) return;
    const token = getToken();
    if (!token) {
      addError("You must be authenticated to delete warehouse maps.");
      return;
    }
    const map = warehouseMaps.find((item) => item.id === selectedWarehouseMapId);
    const label = map?.name ?? `Map #${selectedWarehouseMapId}`;

    setDeletingWarehouseMap(true);
    try {
      await deleteWarehouseMap(selectedWarehouseMapId, token);
      setSelectedWarehouseMapId(null);
      onMapDeleted();
      await loadWarehouseMaps();
      notify(`Deleted warehouse map "${label}".`, "success");
    } catch (error) {
      addError(`Could not delete warehouse map: ${toMessage(error)}`);
    } finally {
      setDeletingWarehouseMap(false);
    }
  }, [
    addError,
    loadWarehouseMaps,
    notify,
    onMapDeleted,
    selectedWarehouseMapId,
    warehouseMaps,
  ]);

  const selectedWarehouseMapName = useMemo(() => {
    if (selectedWarehouseMapId == null) return null;
    return (
      warehouseMaps.find((map) => map.id === selectedWarehouseMapId)?.name ?? null
    );
  }, [selectedWarehouseMapId, warehouseMaps]);

  return {
    warehouseMaps,
    loadingWarehouseMaps,
    selectedWarehouseMapId,
    setSelectedWarehouseMapId,
    creatingMap,
    deletingWarehouseMap,
    loadWarehouseMaps,
    handleCreateWarehouseMap,
    handleDeleteWarehouseMap,
    selectedWarehouseMapName,
  };
}
