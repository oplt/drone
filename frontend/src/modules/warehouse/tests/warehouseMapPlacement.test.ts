import { describe, expect, it } from "vitest";
import {
  formatMapPoint,
  scanTargetsForMapMarkers,
  shelfNormalFromFacing,
} from "../utils/warehouseMapPlacement";

describe("warehouseMapPlacement", () => {
  it("formats map points for display", () => {
    expect(formatMapPoint({ x_m: 1.234, y_m: -2, z_m: 1.6 })).toBe(
      "1.23, -2.00, 1.60",
    );
  });

  it("resolves shelf facing presets", () => {
    expect(shelfNormalFromFacing("+x")).toEqual({ x: 1, y: 0, z: 0 });
    expect(shelfNormalFromFacing("unknown")).toEqual({ x: 0, y: 1, z: 0 });
  });

  it("builds marker payloads from scan targets", () => {
    const markers = scanTargetsForMapMarkers([
      {
        id: 7,
        warehouse_map_id: 1,
        reference_model_id: null,
        dock_station_id: null,
        aisle_code: "A-1",
        rack_code: "R-2",
        shelf_level: 2,
        bin_code: "B-3",
        sku: null,
        barcode: null,
        product_name: null,
        target_point_local_json: { x_m: 1, y_m: 2, z_m: 1.5 },
        scan_pose_local_json: { x_m: 1, y_m: 0.8, z_m: 1.5, yaw_deg: 90 },
        shelf_normal_local_json: null,
        standoff_m: 1.2,
        hover_time_s: 3,
        scan_timeout_s: 8,
        priority: 100,
        active: true,
        created_at: "",
        updated_at: "",
      },
    ]);

    expect(markers).toHaveLength(1);
    expect(markers[0]?.label).toBe("A-1 / R-2 / B-3");
    expect(markers[0]?.scanPose.yaw_deg).toBe(90);
  });
});
