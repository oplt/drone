import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../../test/msw/server";
import { createTestQueryWrapper } from "../../../test/renderWithProviders";
import { useWarehousePreflightRun } from "../hooks/useWarehousePreflightRun";

describe("useWarehousePreflightRun", () => {
  it("stops polling when run status is complete", async () => {
    let polls = 0;
    server.use(
      http.get("*/warehouse/preflight/runs/run-done", () => {
        polls += 1;
        return HttpResponse.json({
          run_id: "run-done",
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
            categories: {},
            note: "",
          },
        });
      }),
    );

    const { result } = renderHook(
      () => useWarehousePreflightRun("token", "run-done"),
      { wrapper: createTestQueryWrapper() },
    );

    await waitFor(() => expect(result.current.data?.status).toBe("complete"));
    await new Promise((resolve) => setTimeout(resolve, 2500));
    expect(polls).toBe(1);
  });

  it("is disabled without token or run id", () => {
    const { result } = renderHook(() => useWarehousePreflightRun(null, null), {
      wrapper: createTestQueryWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });
});
