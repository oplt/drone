import { describe, expect, it } from "vitest";
import {
  buildStartScanTooltip,
  buildWarehouseSystemStatusItems,
} from "../utils/warehouseSystemStatus";

describe("warehouseSystemStatus", () => {
  it("marks preflight blocked when checks have not passed", () => {
    const items = buildWarehouseSystemStatusItems({
      droneConnected: true,
      wsConnected: true,
      viewingScanReplay: false,
      scannedMapReplayHasData: false,
      activeFlightId: null,
      liveChunkCount: 0,
      warehousePreflightPassed: false,
      missionState: "idle",
    });
    expect(items.find((item) => item.label === "Preflight")?.status).toBe(
      "blocked",
    );
  });

  it("describes scan tooltip blockers in priority order", () => {
    expect(
      buildStartScanTooltip({
        warehousePreflightPassed: false,
        selectedWarehouseMapId: 1,
        selectedSensorRigId: 2,
        sensorRigReady: true,
        perceptionReady: true,
      }),
    ).toContain("preflight");
  });
});
