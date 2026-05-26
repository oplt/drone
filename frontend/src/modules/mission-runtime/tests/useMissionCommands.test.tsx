import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../../test/msw/server";
import { useMissionCommands } from "../hooks/useMissionCommands";

vi.mock("../../session", () => ({
  getSessionMarker: () => "test-token",
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useMissionCommands", () => {
  it("issues a pause command and refreshes audit data", async () => {
    server.use(
      http.post("*/tasks/missions/flight-1/commands/pause", () =>
        HttpResponse.json({
          flight_id: "flight-1",
          command_id: "cmd-1",
          command: "pause",
          idempotency_key: "key-1",
          state_before: "running",
          state_after: "paused",
          accepted: true,
          message: "paused",
          requested_at: 1,
        }),
      ),
      http.get("*/tasks/missions/flight-1/commands", () =>
        HttpResponse.json([
          {
            command_id: "cmd-1",
            command: "pause",
            idempotency_key: "key-1",
            requested_by_user_id: 1,
            requested_at: 1,
            state_before: "running",
            state_after: "paused",
            accepted: true,
            message: "paused",
          },
        ]),
      ),
      http.get("*/tasks/missions/flight-1/transitions", () => HttpResponse.json([])),
      http.get("*/telemetry/ops-health", () =>
        HttpResponse.json({
          status: "healthy",
          generated_at: 1,
          telemetry: {
            running: true,
            source_connected: true,
            active_connections: 1,
            last_update: 1,
            has_recent_update: true,
            recent_threshold_sec: 5,
          },
          video: { available: true, healthy: true, fps: 24 },
          queues: {
            db_event: { depth: 1, capacity: 10, utilization_pct: 10 },
            db_lifecycle: { depth: 1, capacity: 10, utilization_pct: 10 },
            raw_event: { depth: 1, capacity: 10, utilization_pct: 10 },
          },
          runtime_metrics: {},
          shadow: {
            shadow_mode_active: false,
            old_path: {
              writes_attempted: 0,
              writes_ok: 0,
              writes_failed: 0,
              error_rate_pct: 0,
            },
            new_path: {
              events_enqueued: 0,
              dropped_db_events: 0,
              worker_batches_completed: 0,
            },
            interpretation: "ok",
          },
          alerts: [],
        }),
      ),
    );

    const { result } = renderHook(
      () =>
        useMissionCommands({
          flightId: "flight-1",
          missionStatus: {
            mission_lifecycle: { state: "running", flight_id: "flight-1" },
            command_capabilities: { pause: true, resume: false, abort: true },
          },
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.opsHealth?.status).toBe("healthy");
    });

    await act(async () => {
      await result.current.issueCommand("pause");
    });

    expect(result.current.message).toContain("paused");
    expect(result.current.error).toBeNull();
    await waitFor(() => {
      expect(result.current.recentAudit[0]?.command).toBe("pause");
    });
  });

  it("surfaces command mutation failures", async () => {
    server.use(
      http.post("*/tasks/missions/flight-1/commands/abort", () =>
        HttpResponse.json({ detail: "abort blocked" }, { status: 409 }),
      ),
      http.get("*/tasks/missions/flight-1/commands", () => HttpResponse.json([])),
      http.get("*/tasks/missions/flight-1/transitions", () => HttpResponse.json([])),
      http.get("*/telemetry/ops-health", () =>
        HttpResponse.json({
          status: "degraded",
          generated_at: 1,
          telemetry: {
            running: false,
            source_connected: false,
            active_connections: 0,
            last_update: 0,
            has_recent_update: false,
            recent_threshold_sec: 5,
          },
          video: { available: false },
          queues: {
            db_event: { depth: 0, capacity: 10, utilization_pct: 0 },
            db_lifecycle: { depth: 0, capacity: 10, utilization_pct: 0 },
            raw_event: { depth: 0, capacity: 10, utilization_pct: 0 },
          },
          runtime_metrics: {},
          shadow: {
            shadow_mode_active: false,
            old_path: {
              writes_attempted: 0,
              writes_ok: 0,
              writes_failed: 0,
              error_rate_pct: 0,
            },
            new_path: {
              events_enqueued: 0,
              dropped_db_events: 0,
              worker_batches_completed: 0,
            },
            interpretation: "ok",
          },
          alerts: [],
        }),
      ),
    );

    const { result } = renderHook(
      () =>
        useMissionCommands({
          flightId: "flight-1",
          missionStatus: {
            mission_lifecycle: { state: "running", flight_id: "flight-1" },
          },
        }),
      { wrapper },
    );

    await act(async () => {
      await expect(result.current.issueCommand("abort")).rejects.toThrow();
    });

    expect(result.current.error).toContain("abort blocked");
  });
});
