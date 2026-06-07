import { useCallback, useEffect, useRef, useState } from "react";
import { emitAppLog, type AppLogEvent } from "../../../shared/logging";

type TelemetryWebSocketOptions = {
  enabled?: boolean;
  onTelemetry?: (data: TelemetrySnapshot) => void;
  onMessage?: (message: TelemetrySocketPayload) => void;
};

type TelemetryObject = Record<string, unknown>;
type TelemetrySnapshot = TelemetryObject & {
  battery?: TelemetryObject;
  gps?: TelemetryObject;
  link?: TelemetryObject;
  position?: TelemetryObject;
  status?: TelemetryObject;
  wind?: TelemetryObject;
};
type TelemetrySocketPayload = TelemetrySnapshot | string | null;

type Subscriber = {
  onState: (state: SharedTelemetryState) => void;
  onTelemetry?: (data: TelemetrySnapshot) => void;
  onMessage?: (message: TelemetrySocketPayload) => void;
};

type SharedTelemetryState = {
  telemetry: TelemetrySnapshot | null;
  isConnected: boolean;
  error: string | null;
  reconnectAttempt: number;
};

const state: SharedTelemetryState = {
  telemetry: null,
  isConnected: false,
  error: null,
  reconnectAttempt: 0,
};

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let pingTimer: number | null = null;
let closeTimer: number | null = null;
let attempt = 0;
let explicitlyClosed = false;
const subscribers = new Set<Subscriber>();
let websocketFactory: ((url: string) => WebSocket) | null = null;

export function setTelemetryWebSocketFactoryForTests(
  factory: ((url: string) => WebSocket) | null,
) {
  websocketFactory = factory;
  if (factory === null) {
    subscribers.clear();
    disconnectShared({ clearTelemetry: true });
  }
}

function notify() {
  subscribers.forEach((subscriber) => subscriber.onState({ ...state }));
}

function wsUrl(): string {
  const apiBaseRaw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const apiBase = (apiBaseRaw?.trim() || "").replace(/\/$/, "");
  if (!apiBase) {
    return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/telemetry`;
  }
  if (apiBase.startsWith("http://") || apiBase.startsWith("https://")) {
    return `${apiBase.replace(/^http/, "ws")}/ws/telemetry`;
  }
  const prefix = apiBase.startsWith("/") ? apiBase : `/${apiBase}`;
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${prefix}/ws/telemetry`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

async function parseMessage(data: unknown): Promise<TelemetrySocketPayload> {
  try {
    const parsed =
      typeof data === "string"
        ? JSON.parse(data)
        : data instanceof Blob
          ? JSON.parse(await data.text())
          : data instanceof ArrayBuffer
            ? JSON.parse(new TextDecoder("utf-8").decode(data))
            : null;
    if (typeof parsed === "string" || isRecord(parsed)) return parsed;
    return null;
  } catch {
    if (typeof data === "string") return data;
    return null;
  }
}

function telemetryFromMessage(msg: TelemetrySocketPayload): TelemetrySnapshot | null {
  if (!isRecord(msg)) return null;
  if (msg.type === "telemetry") {
    return isRecord(msg.data) ? (msg.data as TelemetrySnapshot) : null;
  }
  if (msg.type) {
    return null;
  }
  return msg as TelemetrySnapshot;
}

function clearTimers() {
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  if (pingTimer) window.clearInterval(pingTimer);
  if (closeTimer) window.clearTimeout(closeTimer);
  reconnectTimer = null;
  pingTimer = null;
  closeTimer = null;
}

function connectShared() {
  if (closeTimer) {
    window.clearTimeout(closeTimer);
    closeTimer = null;
  }
  if (
    socket?.readyState === WebSocket.OPEN ||
    socket?.readyState === WebSocket.CONNECTING
  ) {
    return;
  }
  explicitlyClosed = false;
  attempt += 1;
  const currentAttempt = attempt;
  socket = websocketFactory?.(wsUrl()) ?? new globalThis.WebSocket(wsUrl());

  socket.onopen = () => {
    state.isConnected = true;
    state.error = null;
    state.reconnectAttempt = 0;
    attempt = 0;
    emitAppLog({
      level: "info",
      source: "websocket",
      message: "Telemetry websocket connected",
    });
    notify();
    if (pingTimer) window.clearInterval(pingTimer);
    pingTimer = window.setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  };

  socket.onmessage = async (event) => {
    const msg = await parseMessage(event.data);
    if (msg === "pong" || (isRecord(msg) && msg.type === "pong")) return;
    if (isRecord(msg) && msg.type === "app_log" && msg.data) {
      emitAppLog(msg.data as AppLogEvent, { mirrorToConsole: false });
      subscribers.forEach((subscriber) => subscriber.onMessage?.(msg));
      return;
    }
    subscribers.forEach((subscriber) => subscriber.onMessage?.(msg));
    const telemetry = telemetryFromMessage(msg);
    if (telemetry) {
      state.telemetry = telemetry;
      subscribers.forEach((subscriber) => subscriber.onTelemetry?.(telemetry));
      notify();
    }
  };

  socket.onerror = () => {
    state.error = "WebSocket connection error";
    emitAppLog({
      level: "error",
      source: "websocket",
      message: "Telemetry websocket connection error",
      details: { attempt: currentAttempt },
    });
    notify();
  };

  socket.onclose = (event) => {
    socket = null;
    state.isConnected = false;
    notify();
    if (pingTimer) window.clearInterval(pingTimer);
    pingTimer = null;
    if (explicitlyClosed || event.code === 1000 || event.code === 1008) return;
    if (subscribers.size === 0) return;
    const nextAttempt = currentAttempt + 1;
    if (nextAttempt > 10) {
      state.error = "Max reconnection attempts reached";
      emitAppLog({
        level: "critical",
        source: "websocket",
        message: "Telemetry websocket could not reconnect",
        details: { close_code: event.code, close_reason: event.reason },
      });
      notify();
      return;
    }
    state.reconnectAttempt = nextAttempt;
    notify();
    const delay = Math.min(
      1000 * Math.pow(2, Math.max(0, nextAttempt - 1)),
      30000,
    );
    reconnectTimer = window.setTimeout(connectShared, delay);
  };
}

function disconnectShared({ clearTelemetry = false } = {}) {
  clearTimers();
  explicitlyClosed = true;
  if (socket) {
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    if (
      socket.readyState === WebSocket.OPEN ||
      socket.readyState === WebSocket.CONNECTING
    ) {
      socket.close(1000, "No telemetry subscribers");
    }
    socket = null;
  }
  state.isConnected = false;
  state.reconnectAttempt = 0;
  if (clearTelemetry) {
    state.telemetry = null;
    state.error = null;
  }
  notify();
}

function disconnectSharedWhenIdle() {
  if (closeTimer) window.clearTimeout(closeTimer);
  closeTimer = window.setTimeout(() => {
    closeTimer = null;
    if (subscribers.size === 0) disconnectShared();
  }, 250);
}

export function useTelemetryStream(options: TelemetryWebSocketOptions = {}) {
  const enabled = options.enabled ?? false;
  const [snapshot, setSnapshot] = useState<SharedTelemetryState>({ ...state });
  const subscriberRef = useRef<Subscriber>({
    onState: setSnapshot,
    onTelemetry: options.onTelemetry,
    onMessage: options.onMessage,
  });

  useEffect(() => {
    subscriberRef.current.onState = setSnapshot;
    subscriberRef.current.onTelemetry = options.onTelemetry;
    subscriberRef.current.onMessage = options.onMessage;
  }, [options.onMessage, options.onTelemetry]);

  useEffect(() => {
    const subscriber = subscriberRef.current;
    if (!enabled) return undefined;
    subscribers.add(subscriber);
    subscriber.onState({ ...state });
    connectShared();
    return () => {
      subscribers.delete(subscriber);
      if (subscribers.size === 0) disconnectSharedWhenIdle();
    };
  }, [enabled]);

  const reconnect = useCallback(() => {
    if (!enabled) return;
    attempt = 0;
    disconnectShared({ clearTelemetry: false });
    connectShared();
  }, [enabled]);

  const disconnect = useCallback(() => {
    if (subscriberRef.current) subscribers.delete(subscriberRef.current);
    if (subscribers.size === 0) disconnectShared({ clearTelemetry: true });
  }, []);

  return {
    telemetry: snapshot.telemetry,
    isConnected: snapshot.isConnected,
    error: snapshot.error,
    reconnect,
    disconnect,
    reconnectAttempt: snapshot.reconnectAttempt,
  };
}

export const useTelemetryWebSocket = useTelemetryStream;
export default useTelemetryStream;
