import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../../test/msw/server";
import { useRunWarehousePreflight } from "../hooks/useRunWarehousePreflight";

vi.mock("../../mission-runtime/api/telemetryConnectApi", () => ({
  connectDroneTelemetry: vi.fn(() => Promise.reject(new Error("offline"))),
}));

describe("useRunWarehousePreflight", () => {
  it("finishes immediately on terminal preflight blockers", async () => {
    const requests: URL[] = [];
    server.use(
      http.get("*/warehouse/preflight", ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        return HttpResponse.json(
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
              vehicle_link_ok: true,
              telemetry_stream_ok: true,
              battery_ok: true,
              perception_stable_for_ms: 0,
              perception_required_stable_ms: 8000,
              ros_topic_count: null,
              warehouse_bridge_state: "degraded",
              bridge_url: "http://127.0.0.1:8088",
              last_error: "All connection attempts failed",
              restart_count: 1,
              blocking_reasons: ["ROS bridge unreachable"],
              suggested_actions: ["Retry bridge"],
              categories: {
                bridge: "FAIL",
                stability: "WAITING",
              },
              note: "",
            },
          },
          { status: 503 },
        );
      }),
    );

    const { result } = renderHook(() => useRunWarehousePreflight("token"));

    await act(async () => {
      await result.current.runChecks({
        missionLoaded: true,
        timeoutMs: 30_000,
      });
    });

    expect(result.current.result?.ready_to_fly).toBe(false);
    expect(result.current.running).toBe(false);
    expect(result.current.error).toContain("Preflight blocked");
    expect(requests).toHaveLength(1);
    expect(requests[0].searchParams.get("deep")).toBe("true");
  });
});
