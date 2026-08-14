import { describe, expect, it } from "vitest";
import {
  getWarehouseStartMessage,
  getWarehouseStartPreflight,
} from "../warehousePageSupport";

describe("warehousePageSupport characterization", () => {
  it("extracts preflight payload from structured start errors", () => {
    const error = {
      body: {
        detail: {
          preflight: { overall_status: "fail", checks: [] },
        },
      },
    };
    expect(getWarehouseStartPreflight(error)).toEqual({
      overall_status: "fail",
      checks: [],
    });
  });

  it("formats start failure messages with sensor hints", () => {
    const error = {
      body: {
        detail: {
          user_message: "Warehouse scan blocked",
          missing_required_topics: ["visual_slam_odom"],
        },
      },
    };
    expect(getWarehouseStartMessage(error)).toContain("Warehouse scan blocked");
    expect(getWarehouseStartMessage(error)).toContain("Local odometry");
  });
});
