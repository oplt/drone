import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../../test/msw/server";
import { createTestQueryWrapper } from "../../../test/renderWithProviders";

import {
  useRunWarehousePreflight,
  warehousePreflightPassed,
  warehousePreflightPollIntervalMs,
} from "../hooks/useRunWarehousePreflight";

vi.mock("../../mission-runtime/api/telemetryConnectApi", () => ({
  connectDroneTelemetry: vi.fn(() => Promise.reject(new Error("offline"))),
}));

describe("warehousePreflightPassed", () => {
  it("rejects ready_to_fly when rgb_depth_imu panel shows FAIL", () => {
    expect(
      warehousePreflightPassed({
        ready_to_fly: true,
        bridge_ok: true,
        source_transport_ok: true,
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
        ros_topic_count: 20,
        blocking_reasons: [],
        suggested_actions: [],
        categories: { rgb_depth_imu: "FAIL", sensors: "OK" },
        note: "",
        diagnostics: {
          topics: {
            by_category: {
              rgb: { status: "FAIL" },
              depth: { status: "OK" },
              imu: { status: "OK" },
            },
          },
        },
      }),
    ).toBe(false);
  });
});

describe("useRunWarehousePreflight", () => {
  it("polls preflight runs every 1500ms while running", () => {
    expect(warehousePreflightPollIntervalMs(5_000)).toBe(1500);
  });

  it("backs off preflight run polling after 30 seconds", () => {
    expect(warehousePreflightPollIntervalMs(31_000)).toBe(5000);
    expect(warehousePreflightPollIntervalMs(-1)).toBe(false);
  });

  it("does not poll GET /preflight while refresh run is active", async () => {
    let runPolls = 0;
    const snapshotRequests: URL[] = [];
    server.use(
      http.post("*/warehouse/preflight/refresh", () =>
        HttpResponse.json({
          run_id: "run-active",
          status: "running",
          deep: true,
          force: false,
          mission_loaded: false,
          started_at: new Date().toISOString(),
        }),
      ),
      http.get("*/warehouse/preflight/runs/run-active", () => {
        runPolls += 1;
        return HttpResponse.json({
          run_id: "run-active",
          status: runPolls >= 2 ? "complete" : "running",
          deep: true,
          force: false,
          mission_loaded: false,
          started_at: new Date().toISOString(),
          finished_at: runPolls >= 2 ? new Date().toISOString() : null,
          snapshot:
            runPolls >= 2
              ? {
                  ready_to_fly: true,
                  bridge_ok: true,
                  source_transport_ok: true,
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
                  ros_topic_count: 20,
                  blocking_reasons: [],
                  suggested_actions: [],
                  categories: { rgb_depth_imu: "OK", sensors: "OK" },
                  note: "",
                }
              : null,
        });
      }),
      http.get("*/warehouse/preflight", ({ request }) => {
        snapshotRequests.push(new URL(request.url));
        return HttpResponse.json({
          ready_to_fly: false,
          bridge_ok: false,
          source_transport_ok: null,
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
          blocking_reasons: ["should not be polled during active run"],
          suggested_actions: [],
          categories: { bridge: "WAITING" },
          note: "",
        });
      }),
    );

    const { result } = renderHook(() => useRunWarehousePreflight("token"), {
      wrapper: createTestQueryWrapper(),
    });
    await act(async () => {
      await result.current.runChecks({ timeoutMs: 15_000 });
    });

    expect(runPolls).toBeGreaterThanOrEqual(2);
    expect(snapshotRequests).toHaveLength(0);
    expect(result.current.result?.ready_to_fly).toBe(true);
  });

  it("finishes immediately on terminal preflight blockers", async () => {
    const refreshRequests: URL[] = [];
    const snapshotRequests: URL[] = [];
    server.use(
      http.post("*/warehouse/preflight/refresh", ({ request }) => {
        const url = new URL(request.url);
        refreshRequests.push(url);
        return HttpResponse.json({
          run_id: "run-1",
          status: "running",
          deep: true,
          force: true,
          mission_loaded: true,
          started_at: new Date().toISOString(),
        });
      }),
      http.get("*/warehouse/preflight/runs/run-1", () =>
        HttpResponse.json({
          run_id: "run-1",
          status: "complete",
          deep: true,
          force: false,
          mission_loaded: true,
          started_at: new Date().toISOString(),
          finished_at: new Date().toISOString(),
          snapshot: null,
        }),
      ),
      http.get("*/warehouse/preflight", ({ request }) => {
        const url = new URL(request.url);
        snapshotRequests.push(url);
        return HttpResponse.json(
          {
            ready: false,
            blocking: true,
            ready_to_fly: false,
            bridge_ok: false,
            source_transport_ok: null,
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
              sensors: "FAIL",
              stability: "WAITING",
            },
            note: "",
          },
        );
      }),
    );

    const { result } = renderHook(() => useRunWarehousePreflight("token"), {
      wrapper: createTestQueryWrapper(),
    });

    await act(async () => {
      await result.current.runChecks({
        missionLoaded: true,
        timeoutMs: 30_000,
      });
    });

    expect(result.current.result?.ready_to_fly).toBe(false);
    expect(result.current.running).toBe(false);
    expect(result.current.error).toContain("Preflight blocked");
    expect(refreshRequests).toHaveLength(1);
    expect(refreshRequests[0].searchParams.get("deep")).toBe("true");
    expect(refreshRequests[0].searchParams.get("force")).toBe(null);
    expect(snapshotRequests).toHaveLength(1);
    expect(snapshotRequests[0].searchParams.get("deep")).toBe(null);
  });

  it("issues only one refresh POST for overlapping runChecks calls", async () => {
    let refreshPosts = 0;
    server.use(
      http.post("*/warehouse/preflight/refresh", () => {
        refreshPosts += 1;
        return HttpResponse.json({
          run_id: "run-dedupe",
          status: "running",
          deep: true,
          force: false,
          mission_loaded: false,
          started_at: new Date().toISOString(),
        });
      }),
      http.get("*/warehouse/preflight/runs/run-dedupe", () =>
        HttpResponse.json({
          run_id: "run-dedupe",
          status: "complete",
          deep: true,
          force: false,
          mission_loaded: false,
          started_at: new Date().toISOString(),
          finished_at: new Date().toISOString(),
          snapshot: {
            ready_to_fly: true,
            bridge_ok: true,
            source_transport_ok: true,
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
            ros_topic_count: 20,
            blocking_reasons: [],
            suggested_actions: [],
            categories: { rgb_depth_imu: "OK", sensors: "OK" },
            note: "",
          },
        }),
      ),
    );

    const { result } = renderHook(() => useRunWarehousePreflight("token"), {
      wrapper: createTestQueryWrapper(),
    });
    await act(async () => {
      const first = result.current.runChecks({ timeoutMs: 15_000 });
      const second = result.current.runChecks({ timeoutMs: 15_000 });
      await Promise.all([first, second]);
    });

    expect(refreshPosts).toBe(1);
    expect(result.current.result?.ready_to_fly).toBe(true);
  });
});
