import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  useWorkflowEventStream,
  type WorkflowEventEnvelope,
} from "./useWorkflowEventStream";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readonly withCredentials: boolean;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, Set<(event: Event) => void>>();

  constructor(url: string | URL, options?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(options?.withCredentials);
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    if (typeof listener !== "function") return;
    const values = this.listeners.get(type) ?? new Set();
    values.add(listener);
    this.listeners.set(type, values);
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    if (typeof listener === "function") this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: WorkflowEventEnvelope, lastEventId: string) {
    const event = {
      data: JSON.stringify(data),
      lastEventId,
    } as MessageEvent<string>;
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  FakeEventSource.instances = [];
  window.sessionStorage.clear();
});

describe("useWorkflowEventStream", () => {
  it("replays from the stored cursor, updates it, and reconnects through EventSource", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const path = "/agriculture/analysis-runs/run-1/events";
    window.sessionStorage.setItem(`drone-app:workflow-event:${path}`, "42");
    const onEvent = vi.fn();
    const hook = renderHook(() => useWorkflowEventStream(path, onEvent));
    const source = FakeEventSource.instances[0];

    expect(source.url).toContain("after_id=42");
    expect(source.withCredentials).toBe(true);
    act(() => source.onopen?.());
    expect(hook.result.current).toBe("open");

    const event: WorkflowEventEnvelope = {
      id: 43,
      domain: "agriculture_analysis",
      stream_id: "run-1",
      subject_id: "run-1",
      event_type: "stage.completed",
      payload: { stage: "geospatial_aggregation" },
      created_at: "2026-08-14T12:00:00Z",
    };
    act(() => source.emit("stage.completed", event, "43"));

    expect(onEvent).toHaveBeenCalledWith(event);
    expect(window.sessionStorage.getItem(`drone-app:workflow-event:${path}`)).toBe(
      "43",
    );
    act(() => source.onerror?.());
    expect(hook.result.current).toBe("error");
    hook.unmount();
    expect(source.closed).toBe(true);
  });

  it("reports unsupported so callers can keep polling", () => {
    vi.stubGlobal("EventSource", undefined);
    const { result } = renderHook(() => useWorkflowEventStream("/events", vi.fn()));
    expect(result.current).toBe("unsupported");
  });

  it("reports an error when EventSource initialization fails", async () => {
    class FailingEventSource {
      constructor() {
        throw new Error("SSE unavailable");
      }
    }
    vi.stubGlobal("EventSource", FailingEventSource);

    const { result } = renderHook(() => useWorkflowEventStream("/events", vi.fn()));

    await waitFor(() => expect(result.current).toBe("error"));
  });

  it("continues without cursor persistence when session storage is blocked", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });

    const { result } = renderHook(() => useWorkflowEventStream("/events", vi.fn()));

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(result.current).toBe("connecting");
  });
});
