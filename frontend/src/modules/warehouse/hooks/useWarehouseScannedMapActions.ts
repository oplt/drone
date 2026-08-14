import { useCallback, useState } from "react";
import { getToken } from "../../session";
import { deleteWarehouseScannedMap } from "../api/warehouseMissionsApi";
import { getWarehouseMapId, getWarehouseName, selectScannedMap } from "../scannedMapSelectors";
import type { WarehouseScannedMapResponse } from "../types/missions";
import { toMessage } from "../warehousePageSupport";

type UseWarehouseScannedMapActionsOptions = {
  scannedMaps: WarehouseScannedMapResponse[];
  refetchScannedMaps: () => Promise<{ data?: WarehouseScannedMapResponse[] }>;
  addError: (message: string) => void;
  notify: (message: string, severity: "success" | "info" | "error") => void;
};

export function useWarehouseScannedMapActions({
  scannedMaps,
  refetchScannedMaps,
  addError,
  notify,
}: UseWarehouseScannedMapActionsOptions) {
  const [selectedMapJobId, setSelectedMapJobId] = useState<number | null>(null);
  const [viewerMapJobId, setViewerMapJobId] = useState<number | null>(null);
  const [deletingScannedMap, setDeletingScannedMap] = useState(false);

  const loadScannedMaps = useCallback(
    async (options?: { selectJobId?: number; showInViewer?: boolean }) => {
      const token = getToken();
      if (!token) return [];

      try {
        const records = (await refetchScannedMaps()).data ?? [];

        const explicitJobId = options?.selectJobId;
        if (explicitJobId != null) {
          setSelectedMapJobId(explicitJobId);
          if (options?.showInViewer) {
            setViewerMapJobId(explicitJobId);
          }
        } else {
          setSelectedMapJobId((current) => {
            if (
              current != null &&
              records.some((record) => record.job_id === current)
            ) {
              return current;
            }
            return null;
          });
        }
        return records;
      } catch (error) {
        addError(
          `Scanned warehouse maps could not be loaded: ${toMessage(error)}`,
        );
        return [];
      }
    },
    [addError, refetchScannedMaps],
  );

  const handleDeleteScannedMap = useCallback(
    async (selectedScannedMap: WarehouseScannedMapResponse | null) => {
      if (!selectedScannedMap) return;
      const token = getToken();
      if (!token) {
        addError("You must be authenticated to delete scan results.");
        return;
      }
      const jobId = selectedScannedMap.job_id;
      const label = `${getWarehouseName(selectedScannedMap)} (#${jobId})`;

      setDeletingScannedMap(true);
      try {
        await deleteWarehouseScannedMap(jobId, token);
        setSelectedMapJobId((current) => (current === jobId ? null : current));
        setViewerMapJobId((current) => (current === jobId ? null : current));
        await loadScannedMaps();
        notify(`Deleted scan result "${label}".`, "success");
      } catch (error) {
        addError(`Could not delete scan result: ${toMessage(error)}`);
      } finally {
        setDeletingScannedMap(false);
      }
    },
    [addError, loadScannedMaps, notify],
  );

  const selectedScannedMap = selectScannedMap(scannedMaps, selectedMapJobId);
  const viewerScannedMap = selectScannedMap(scannedMaps, viewerMapJobId);

  const filterScannedMapsForWarehouse = useCallback(
    (selectedWarehouseMapId: number | null) =>
      scannedMaps.filter((map) => {
        if (selectedWarehouseMapId != null) {
          if (getWarehouseMapId(map) !== selectedWarehouseMapId) return false;
        }
        return true;
      }),
    [scannedMaps],
  );

  return {
    selectedMapJobId,
    setSelectedMapJobId,
    viewerMapJobId,
    setViewerMapJobId,
    deletingScannedMap,
    loadScannedMaps,
    handleDeleteScannedMap,
    selectedScannedMap,
    viewerScannedMap,
    filterScannedMapsForWarehouse,
  };
}
