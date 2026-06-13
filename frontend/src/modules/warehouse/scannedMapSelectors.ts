import type { WarehouseScannedMapResponse } from "./types/missions";

export function getWarehouseMapId(map: WarehouseScannedMapResponse): number {
  return map.warehouse_map_id;
}

export function getWarehouseName(map: WarehouseScannedMapResponse): string {
  return map.warehouse_name.trim() || "Warehouse";
}

export function selectScannedMap(
  maps: WarehouseScannedMapResponse[],
  selectedJobId: number | null,
): WarehouseScannedMapResponse | null {
  if (selectedJobId == null) return null;
  return maps.find((map) => map.job_id === selectedJobId) ?? null;
}
