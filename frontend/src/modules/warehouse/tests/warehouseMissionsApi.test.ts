import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../../test/msw/server";
import {
  fetchWarehouseScannedMapQuality,
  listWarehouseScannedMaps,
  startWarehouseExploration,
} from "../api/warehouseMissionsApi";

describe("warehouse missions API", () => {
  it("filters scanned maps by warehouse_map_id", async () => {
    const requestedUrls: string[] = [];
    server.use(
      http.get("*/warehouse/scanned-maps", ({ request }) => {
        requestedUrls.push(request.url);
        return HttpResponse.json([]);
      }),
    );

    await listWarehouseScannedMaps("token", 42);

    const requestedUrl = new URL(requestedUrls[0] ?? "http://test.invalid");
    expect(requestedUrl?.searchParams.get("warehouse_map_id")).toBe("42");
    expect(requestedUrl?.searchParams.has("field_id")).toBe(false);
  });

  it("starts exploration with warehouse map and dock payload", async () => {
    let body: unknown = null;
    server.use(
      http.post("*/warehouse/missions/exploration/start", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          warehouse_map_id: 42,
          warehouse_name: "Warehouse",
          preflight: { overall_status: "passed" },
          mission: { flight_id: "f-1", mission_name: "Explore" },
        });
      }),
    );

    await startWarehouseExploration(
      {
        warehouse_map_id: 42,
        dock_id: 7,
        exploration: {
          max_mission_time_s: 900,
          max_exploration_radius_m: 80,
          minimum_corridor_clearance_m: 1,
          obstacle_clearance_m: 1,
          max_frontier_candidates: 8,
          battery_return_reserve_pct: 30,
        },
      },
      "token",
    );

    expect(body).toMatchObject({ warehouse_map_id: 42, dock_id: 7 });
  });

  it("fetches scanned map quality by job id", async () => {
    const requestedUrls: string[] = [];
    server.use(
      http.get("*/warehouse/scanned-maps/:jobId/quality", ({ request, params }) => {
        requestedUrls.push(request.url);
        return HttpResponse.json({
          job_id: Number(params.jobId),
          source: "simulation",
          report: {},
        });
      }),
    );

    const quality = await fetchWarehouseScannedMapQuality(55, "token");

    expect(quality.job_id).toBe(55);
    expect(quality.source).toBe("simulation");
    expect(requestedUrls[0]).toContain("/warehouse/scanned-maps/55/quality");
  });
});
