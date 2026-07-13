import { describe, expect, it } from "vitest";
import {
  initialWarehousePageState,
  warehousePageReducer,
} from "../warehousePageState";

describe("warehouse page state machine", () => {
  it("keeps drawer and destructive-action state explicit", () => {
    const setup = warehousePageReducer(initialWarehousePageState, {
      type: "open-mode",
      mode: "setup",
    });
    const deleting = warehousePageReducer(setup, {
      type: "request-delete",
      target: { kind: "map", label: "Map 4", onConfirm: () => undefined },
    });

    expect(deleting.mode).toBe("setup");
    expect(deleting.deleteTarget).toMatchObject({ kind: "map", label: "Map 4" });
    expect(
      warehousePageReducer(deleting, { type: "cancel-delete" }).deleteTarget,
    ).toBeNull();
  });
});
