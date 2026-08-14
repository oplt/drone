import { useEffect, useState } from "react";
import { resolveApiUrl } from "./httpClient";

export type WorkflowEventEnvelope = {
  id: number;
  domain: string;
  stream_id: string;
  subject_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WorkflowEventConnection =
  | "connecting"
  | "open"
  | "error"
  | "unsupported";

const lifecycleEventTypes = [
  "run.queued",
  "run.started",
  "run.cancelled",
  "run.failed",
  "run.completed",
  "stage.started",
  "stage.progress",
  "stage.completed",
  "stage.waiting_external",
  "stage.retryable",
  "stage.failed",
  "export.queued",
  "export.completed",
  "training.queued",
  "training.started",
  "training.progress",
  "training.cancelling",
  "training.cancelled",
  "training.failed",
  "training.completed",
] as const;

function readCursor(storageKey: string): string | null {
  try {
    return window.sessionStorage.getItem(storageKey);
  } catch {
    return null;
  }
}

function storeCursor(storageKey: string, cursor: string): void {
  try {
    window.sessionStorage.setItem(storageKey, cursor);
  } catch {
    // Cursor persistence is optional; EventSource can still reconnect normally.
  }
}

export function useWorkflowEventStream(
  path: string | null,
  onEvent: (event: WorkflowEventEnvelope) => void,
): WorkflowEventConnection {
  const [connection, setConnection] = useState<{
    path: string;
    status: Exclude<WorkflowEventConnection, "unsupported">;
  } | null>(null);

  useEffect(() => {
    if (!path || typeof EventSource === "undefined") {
      return;
    }
    const storageKey = `drone-app:workflow-event:${path}`;
    const priorCursor = readCursor(storageKey);
    const separator = path.includes("?") ? "&" : "?";
    const url = resolveApiUrl(
      priorCursor ? `${path}${separator}after_id=${encodeURIComponent(priorCursor)}` : path,
    );
    let closed = false;
    let source: EventSource;
    try {
      source = new EventSource(url, { withCredentials: true });
    } catch {
      queueMicrotask(() => {
        if (!closed) setConnection({ path, status: "error" });
      });
      return () => {
        closed = true;
      };
    }

    const handleEvent = (raw: Event) => {
      const message = raw as MessageEvent<string>;
      try {
        const event = JSON.parse(message.data) as WorkflowEventEnvelope;
        if (message.lastEventId) {
          storeCursor(storageKey, message.lastEventId);
        }
        onEvent(event);
      } catch {
        // A malformed event must not stop native EventSource reconnection.
      }
    };
    lifecycleEventTypes.forEach((name) => source.addEventListener(name, handleEvent));
    source.onopen = () => !closed && setConnection({ path, status: "open" });
    source.onerror = () => !closed && setConnection({ path, status: "error" });

    return () => {
      closed = true;
      lifecycleEventTypes.forEach((name) => source.removeEventListener(name, handleEvent));
      source.close();
    };
  }, [path, onEvent]);

  if (!path || typeof EventSource === "undefined") return "unsupported";
  return connection?.path === path ? connection.status : "connecting";
}
