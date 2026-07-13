import { useQuery } from "@tanstack/react-query";
import { getToken } from "../../session";
import { listWarehouseScannedMaps } from "../api/warehouseMissionsApi";
import type { WarehouseScannedMapResponse } from "../types/missions";

export const warehouseResourceKeys = {
  scannedMaps: (mapId: number | null) => ["warehouse", "scanned-maps", mapId] as const,
};

export function useWarehouseResourceQueries(selectedWarehouseMapId: number | null) {
  const token = getToken();
  const scannedMaps = useQuery<WarehouseScannedMapResponse[]>({
    queryKey: warehouseResourceKeys.scannedMaps(selectedWarehouseMapId),
    queryFn: () => listWarehouseScannedMaps(token!, selectedWarehouseMapId),
    enabled: Boolean(token),
    staleTime: 5_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  });

  return {
    scannedMaps,
  };
}
