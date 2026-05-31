import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../../test/msw/server";
import { fetchWarehouseFlightReadiness } from "../api/warehouseFlightApi";

describe("warehouse flight API", () => {
  it("fetches flight readiness snapshot", async () => {
    server.use(
      http.get("*/warehouse/flight/readiness", () =>
        HttpResponse.json({
          ready_to_arm: false,
          ready_to_takeoff: false,
          ready_for_autonomy: false,
          overall_status: "FAIL",
          current_state: "SYSTEM_CHECK",
          subsystems: {
            bridge: { status: "OK", message: "fresh" },
          },
          blocking_reasons: ["SLAM tracking not stable yet"],
          updated_at: "2026-05-31T12:00:00Z",
          slam_stable_for_ms: 100,
          slam_required_stable_ms: 5000,
        }),
      ),
    );

    const readiness = await fetchWarehouseFlightReadiness("token", { missionLoaded: true });

    expect(readiness.ready_for_autonomy).toBe(false);
    expect(readiness.blocking_reasons[0]).toContain("SLAM");
  });
});
