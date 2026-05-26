import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../../../test/msw/server";
import { useAnalyticsOverview } from "./useAnalyticsOverview";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useAnalyticsOverview", () => {
  it("loads analytics via the shared HTTP client", async () => {
    server.use(
      http.get("*/analytics/overview", () =>
        HttpResponse.json({
          summary: {
            active_flights: 1,
            flights_24h: 2,
            telemetry_24h: 3,
            flight_hours_7d: 4,
            avg_battery_24h: 80,
          },
          trends: { days: [], flight_hours: [], flight_counts: [], telemetry_counts: [] },
          coverage: [],
          recent_flights: [],
          events: [],
          system: {
            telemetry_running: true,
            active_connections: 1,
            last_update: Date.now(),
            mavlink_connected: false,
          },
        }),
      ),
    );

    const { result } = renderHook(() => useAnalyticsOverview(60_000), { wrapper });

    await waitFor(() => {
      expect(result.current.hasData).toBe(true);
    });

    expect(result.current.data?.summary.active_flights).toBe(1);
    expect(result.current.error).toBeNull();
  });
});
