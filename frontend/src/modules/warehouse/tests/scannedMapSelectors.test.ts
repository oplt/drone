import { describe, expect, it } from "vitest";
import {
  getWarehouseMapId,
  getWarehouseName,
  selectScannedMap,
} from "../scannedMapSelectors";
import type { WarehouseScannedMapResponse } from "../types/missions";

const makeScannedMap = (
  overrides: Partial<WarehouseScannedMapResponse>,
): WarehouseScannedMapResponse => ({
  job_id: 1,
  model_id: 10,
  model_version: 1,
  warehouse_map_id: 100,
  warehouse_name: "Main Warehouse",
  status: "ready",
  created_at: "2026-05-29T12:00:00Z",
  finished_at: null,
  polygon_local_m: [
    [0, 0],
    [1, 0],
    [1, 1],
  ],
  assets: [],
  ...overrides,
});

describe("warehouse scanned map selectors", () => {
  it("reads current backend warehouse fields", () => {
    const map = makeScannedMap({
      warehouse_map_id: 22,
      warehouse_name: "Aisle Block",
    });

    expect(getWarehouseMapId(map)).toBe(22);
    expect(getWarehouseName(map)).toBe("Aisle Block");
  });

  it("selects requested scanned map without implicit fallback", () => {
    const first = makeScannedMap({ job_id: 11 });
    const second = makeScannedMap({ job_id: 12 });

    expect(selectScannedMap([first, second], 12)).toBe(second);
    expect(selectScannedMap([first, second], 99)).toBeNull();
    expect(selectScannedMap([first, second], null)).toBeNull();
    expect(selectScannedMap([], 99)).toBeNull();
  });
});
