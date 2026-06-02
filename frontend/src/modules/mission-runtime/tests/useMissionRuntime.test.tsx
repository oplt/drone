import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "../../../test/msw/server";
import { useMissionRuntime } from "../hooks/useMissionRuntime";
import {
  setTelemetryWebSocketFactoryForTests,
  useTelemetryStream,
} from "../hooks/useTelemetryStream";

vi.mock("../../session", () => ({
  getSessionMarker: () => "test-token",
}));

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason?: string }) => void) | null = null;
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
    this.onclose?.({ code: 1000, reason: "test" });
  }

  send() {}
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useMissionRuntime", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
    setTelemetryWebSocketFactoryForTests(
      (url: string) => new MockWebSocket(url) as unknown as WebSocket,
    );
    MockWebSocket.instances = [];
  });

  afterEach(() => {
    setTelemetryWebSocketFactoryForTests(null);
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
    act(() => {
      socket.onerror?.();
    });

    await waitFor(() => {
      expect(result.current.connection).toBe("degraded");
      expect(result.current.telemetryError).toBeTruthy();
    });
  });

  it("shares one telemetry websocket across runtime hooks", async () => {
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
    const first = renderHook(
      () => useMissionRuntime({ onError, alwaysConnect: true }),
      {
        wrapper,
      },
    );
    const second = renderHook(
      () => useMissionRuntime({ onError, alwaysConnect: true }),
      {
        wrapper,
      },
    );

    await waitFor(() => {
      expect(first.result.current.missionStatus?.flight_id).toBe("flight-1");
      expect(second.result.current.missionStatus?.flight_id).toBe("flight-1");
      expect(MockWebSocket.instances.length).toBe(1);
    });

    first.unmount();
    second.unmount();
  });
  it("creates one shared websocket for multiple telemetry subscribers", async () => {
    const first = renderHook(() => useTelemetryStream({ enabled: true }));
    const second = renderHook(() => useTelemetryStream({ enabled: true }));

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    first.unmount();
    second.unmount();
  });
});
