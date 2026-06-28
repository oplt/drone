import { describe, expect, it } from "vitest";
import type { WarehouseCoordinateFrame } from "../api/warehouseInspectionApi";
import {
  createWarehouseSceneTransform,
  resolveDisplayedFrame,
  sceneToWarehouseMap,
  warehouseMapToScene,
} from "../utils/warehouseSceneCoordinates";

const frame: WarehouseCoordinateFrame = {
  id: 42,
  warehouse_map_id: 7,
  version: 3,
  parent_frame_id: "warehouse_map",
  child_frame_id: "odom",
  units: "m",
  axis_convention: "ENU",
  handedness: "right",
  transform: {
    translation: { x: 10, y: 20, z: 1 },
    rotation: { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 },
  },
  source: "fiducial",
  status: "locked",
  confidence: 0.98,
  covariance: [],
  created_at: "2026-01-01T00:00:00Z",
  locked_at: "2026-01-01T00:00:00Z",
  superseded_at: null,
};

describe("warehouse scene coordinates", () => {
  it("converts odom scene points into warehouse_map", () => {
    const transform = createWarehouseSceneTransform("odom", frame);
    expect(transform).not.toBeNull();
    const warehouse = sceneToWarehouseMap({ x_m: 1, y_m: 0, z_m: 2 }, transform!);
    expect(warehouse.x_m).toBeCloseTo(10);
    expect(warehouse.y_m).toBeCloseTo(21);
    expect(warehouse.z_m).toBeCloseTo(3);
  });

  it("round-trips warehouse markers through scene coordinates", () => {
    const transform = createWarehouseSceneTransform("odom", frame)!;
    const point = { x_m: 7.2, y_m: -3.1, z_m: 2.4 };
    const roundTrip = sceneToWarehouseMap(warehouseMapToScene(point, transform), transform);
    expect(roundTrip.x_m).toBeCloseTo(point.x_m);
    expect(roundTrip.y_m).toBeCloseTo(point.y_m);
    expect(roundTrip.z_m).toBeCloseTo(point.z_m);
  });

  it("rejects mixed or unsupported display frames", () => {
    expect(resolveDisplayedFrame(["odom", "warehouse_map"])).toBeNull();
    expect(createWarehouseSceneTransform("camera", frame)).toBeNull();
  });
});
