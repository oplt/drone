import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  computeWarehouseScanPose,
  listWarehouseScanTargets,
} from "../api/warehouseInspectionApi";
import { useWarehouseMapPlacement } from "../hooks/useWarehouseMapPlacement";

vi.mock("../api/warehouseInspectionApi", () => ({
  computeWarehouseScanPose: vi.fn(),
  listWarehouseScanTargets: vi.fn(),
}));

describe("useWarehouseMapPlacement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listWarehouseScanTargets).mockResolvedValue({
      items: [],
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
