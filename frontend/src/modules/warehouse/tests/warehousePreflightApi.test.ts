import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../../test/msw/server";
import { fetchWarehousePreflight } from "../api/warehousePreflightApi";

describe("warehouse preflight API", () => {
  it("returns blocking preflight payload from 503 failed dependency response", async () => {
    server.use(
      http.get("*/warehouse/preflight", () =>
        HttpResponse.json(
          {
            detail: {
              ready: false,
              blocking: true,
              ready_to_fly: false,
              bridge_ok: false,
              gazebo_ok: null,
              sensors_ok: false,
              odom_ok: false,
              localization_ok: false,
              tf_ok: false,
              nvblox_ok: null,
              stability_ok: false,
              vehicle_link_ok: false,
              telemetry_stream_ok: false,
              battery_ok: false,
              perception_stable_for_ms: 0,
              perception_required_stable_ms: 8000,
              ros_topic_count: null,
              warehouse_bridge_state: "degraded",
              bridge_url: "http://127.0.0.1:8088",
              last_error: "All connection attempts failed",
              restart_count: 1,
              blocking_reasons: ["ROS bridge unreachable"],
              suggested_actions: ["Retry bridge"],
              categories: { bridge: "FAIL" },
              note: "",
            },
          },
          { status: 503 },
        ),
      ),
    );

    const result = await fetchWarehousePreflight("token", {
      missionLoaded: true,
    });

    expect(result.ready_to_fly).toBe(false);
    expect(result.blocking).toBe(true);
    expect(result.warehouse_bridge_state).toBe("degraded");
    expect(result.blocking_reasons[0]).toContain("ROS bridge");
  });

  it("returns expected not-ready payload from service unavailable error envelope", async () => {
    server.use(
      http.get("*/warehouse/preflight", () =>
        HttpResponse.json(
          {
            error: {
              code: "SERVICE_UNAVAILABLE",
              message: "Request failed",
              details: {
                ready: false,
                blocking: true,
                ready_to_fly: false,
                bridge_ok: true,
                gazebo_ok: true,
                sensors_ok: true,
                odom_ok: true,
                localization_ok: true,
                tf_ok: true,
                nvblox_ok: null,
                stability_ok: false,
                vehicle_link_ok: true,
                telemetry_stream_ok: true,
                battery_ok: true,
                perception_stable_for_ms: 0,
                perception_required_stable_ms: 8000,
                ros_topic_count: 17,
                warehouse_bridge_state: "ready",
                bridge_url: "http://127.0.0.1:8088",
                last_error: "Waiting for perception stability window",
                restart_count: 1,
                blocking_reasons: ["Waiting for perception stability window"],
                suggested_actions: ["Wait until perception remains stable for 8 seconds"],
                categories: { bridge: "OK", stability: "WAITING" },
                diagnostics: {
                  topics: {
                    required_missing: [],
                    deferred_missing: ["/nvblox_node/mesh"],
                    by_category: {
                      rgb: { topic: "/warehouse/front/rgbd/image", status: "OK" },
                      depth: { topic: "/warehouse/front/rgbd/depth_image", status: "OK" },
                      imu: { topic: "/imu", status: "OK" },
                      lidar_scan: { topic: "/scan", status: "OK" },
                    },
                  },
                  stability: { remaining_ms: 8000 },
                },
                note: "",
              },
            },
          },
          { status: 503 },
        ),
      ),
    );

    const result = await fetchWarehousePreflight("token", {
      missionLoaded: true,
      deep: true,
    });

    expect(result.ready_to_fly).toBe(false);
    expect(result.bridge_ok).toBe(true);
    expect(result.categories.bridge).toBe("OK");
    expect(result.diagnostics?.topics?.required_missing).toEqual([]);
    expect(result.diagnostics?.topics?.deferred_missing).toEqual(["/nvblox_node/mesh"]);
    expect(result.diagnostics?.topics?.by_category?.lidar_scan?.status).toBe("OK");
    expect(result.diagnostics?.stability?.remaining_ms).toBe(8000);
  });

  it("sends explicit deep preflight query when requested", async () => {
    server.use(
      http.get("*/warehouse/preflight", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("mission_loaded")).toBe("true");
        expect(url.searchParams.get("deep")).toBe("true");
        return HttpResponse.json({
          ready: true,
          blocking: false,
          ready_to_fly: true,
          bridge_ok: true,
          gazebo_ok: null,
          sensors_ok: true,
          odom_ok: true,
          localization_ok: true,
          tf_ok: true,
          nvblox_ok: null,
          stability_ok: true,
          vehicle_link_ok: true,
          telemetry_stream_ok: true,
          battery_ok: true,
          perception_stable_for_ms: 8000,
          perception_required_stable_ms: 8000,
          ros_topic_count: 42,
          warehouse_bridge_state: "ready",
          blocking_reasons: [],
          suggested_actions: [],
          categories: { bridge: "OK" },
          note: "",
        });
      }),
    );

    const result = await fetchWarehousePreflight("token", {
      missionLoaded: true,
      deep: true,
    });

    expect(result.ready_to_fly).toBe(true);
  });
});
