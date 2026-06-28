import { describe, expect, it } from "vitest";
import {
  entityToSceneNode,
  layoutToScene,
  moveEntity,
  snapValue,
} from "../utils/warehouseLayoutScene";

describe("warehouse layout scene adapter", () => {
  it("keeps explicit warehouse_map frame and metric geometry", () => {
    const node = entityToSceneNode("bins", {
      id: 7,
      parent_id: 4,
      code: "B7",
      geometry: { x_m: 2, y_m: 3, z_m: 1.5, width_m: 0.8 },
    });
    expect(node).toMatchObject({
      id: "bins:7",
      frameId: "warehouse_map",
      parentId: 4,
      x: 2,
      y: 3,
      z: 1.5,
      width: 0.8,
    });
  });

  it("snaps moves without mutating source geometry", () => {
    const source = { id: 1, code: "A1", geometry: { x_m: 0, y_m: 0 } };
    const moved = moveEntity(source, 1.13, 2.37, 0.25);
    expect(moved.geometry).toMatchObject({ x_m: 1.25, y_m: 2.25 });
    expect(source.geometry).toEqual({ x_m: 0, y_m: 0 });
    expect(snapValue(1.24, 0)).toBe(1.24);
  });

  it("flattens hierarchy into stable scene nodes", () => {
    const nodes = layoutToScene({
      aisles: [{ id: 1, code: "A", geometry: {} }],
      racks: [{ id: 2, parent_id: 1, code: "R", geometry: {} }],
      shelves: [],
      bins: [],
      zones: [],
    });
    expect(nodes.map((node) => node.id)).toEqual(["aisles:1", "racks:2"]);
  });
});
