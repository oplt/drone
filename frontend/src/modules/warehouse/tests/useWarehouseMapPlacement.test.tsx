import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  computeWarehouseScanPose,
  fetchActiveWarehouseCoordinateFrame,
  listWarehouseScanTargets,
} from "../api/warehouseInspectionApi";
import { useWarehouseMapPlacement } from "../hooks/useWarehouseMapPlacement";

vi.mock("../api/warehouseInspectionApi", () => ({
  computeWarehouseScanPose: vi.fn(),
  fetchActiveWarehouseCoordinateFrame: vi.fn(),
  listWarehouseScanTargets: vi.fn(),
}));

describe("useWarehouseMapPlacement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listWarehouseScanTargets).mockResolvedValue({
      items: [],
      next_cursor: null,
      total: 0,
      limit: 200,
      offset: 0,
    });
    vi.mocked(computeWarehouseScanPose).mockResolvedValue({
      scan_pose: {
        frame_id: "warehouse_map",
        x_m: 1,
        y_m: 2,
        z_m: 3,
        yaw_deg: 0,
      },
    });
    vi.mocked(fetchActiveWarehouseCoordinateFrame).mockResolvedValue({
      id: 42,
      warehouse_map_id: 1,
      version: 3,
      parent_frame_id: "warehouse_map",
      child_frame_id: "odom",
      units: "m",
      axis_convention: "ENU",
      handedness: "right",
      transform: {
        translation: { x: 10, y: 20, z: 0 },
        rotation: { x: 0, y: 0, z: 0, w: 1 },
      },
      source: "test",
      status: "locked",
      confidence: 1,
      covariance: [],
      created_at: "2026-01-01T00:00:00Z",
      locked_at: "2026-01-01T00:00:00Z",
      superseded_at: null,
    });
  });

  it("debounces rapid scan-pose adjustments", async () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useWarehouseMapPlacement({
        warehouseMapId: 1,
        token: "token",
        onError,
      }),
    );
    await act(async () => undefined);

    act(() => {
      result.current.viewerProps.onPick({ x_m: 1, y_m: 2, z_m: 3 });
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200));
      result.current.panelProps.setStandoffM(1.8);
    });
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(computeWarehouseScanPose).not.toHaveBeenCalled();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 75));
    });
    expect(computeWarehouseScanPose).toHaveBeenCalledTimes(1);
    expect(computeWarehouseScanPose).toHaveBeenCalledWith(
      expect.objectContaining({ standoff_m: 1.8 }),
      "token",
      expect.any(AbortSignal),
    );
  });
});
