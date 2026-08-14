import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "../../../test/msw/server";
import { agricultureKeys } from "./queryKeys";
import { useAgricultureFindings } from "./analysis/hooks";

function createWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

describe("agriculture run-scoped polling", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls findings while analysis run is active", async () => {
    let calls = 0;
    server.use(
      http.get("*/agriculture/analysis-runs/run-1/findings", () => {
        calls += 1;
        return HttpResponse.json({
          schema_version: "agriculture.v1",
          policy_version: "v1",
          run_id: "run-1",
          limit: 25,
          total_candidates: 0,
          items: [],
          hotspots: { type: "FeatureCollection", features: [] },
        });
      }),
    );

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(agricultureKeys.analysisRun("run-1"), {
      id: "run-1",
      status: "running",
    });

    renderHook(() => useAgricultureFindings("run-1"), {
      wrapper: createWrapper(client),
    });

    await waitFor(() => {
      expect(calls).toBeGreaterThanOrEqual(1);
    });

    const initialCalls = calls;
    await vi.advanceTimersByTimeAsync(5100);

    await waitFor(() => {
      expect(calls).toBeGreaterThan(initialCalls);
    });
  });

  it("stops polling findings after terminal analysis run status", async () => {
    let calls = 0;
    server.use(
      http.get("*/agriculture/analysis-runs/run-1/findings", () => {
        calls += 1;
        return HttpResponse.json({
          schema_version: "agriculture.v1",
          policy_version: "v1",
          run_id: "run-1",
          limit: 25,
          total_candidates: 0,
          items: [],
          hotspots: { type: "FeatureCollection", features: [] },
        });
      }),
    );

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(agricultureKeys.analysisRun("run-1"), {
      id: "run-1",
      status: "completed",
    });

    renderHook(() => useAgricultureFindings("run-1"), {
      wrapper: createWrapper(client),
    });

    await waitFor(() => {
      expect(calls).toBe(1);
    });

    await vi.advanceTimersByTimeAsync(15_000);
    expect(calls).toBe(1);
  });
});
