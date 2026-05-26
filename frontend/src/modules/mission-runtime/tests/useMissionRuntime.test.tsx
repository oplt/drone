import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "../../../test/msw/server";
import { useMissionRuntime } from "../hooks/useMissionRuntime";

vi.mock("../../session", () => ({
  getSessionMarker: () => "test-token",
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  readyState = 0;

  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  send() {}
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useMissionRuntime", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    MockWebSocket.instances = [];
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    MockWebSocket.instances = [];
  });

  it("reports degraded telemetry when websocket errors", async () => {

    server.use(
      http.get("*/tasks/flight/status", () =>
        HttpResponse.json({
          orchestrator: { drone_connected: true },
          telemetry: { running: true },
          flight_id: "flight-1",
        }),
      ),
    );

    const onError = vi.fn();
    const { result } = renderHook(
      () => useMissionRuntime({ onError, alwaysConnect: true }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.missionStatus?.flight_id).toBe("flight-1");
    });

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThan(0);
    });

    const socket = MockWebSocket.instances.at(-1)!;
    socket.onerror?.();

    await waitFor(() => {
      expect(result.current.connection).toBe("degraded");
      expect(result.current.telemetryError).toBeTruthy();
    });
  });
});
