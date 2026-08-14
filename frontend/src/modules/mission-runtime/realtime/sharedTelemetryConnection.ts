import { emitAppLog, type AppLogEvent } from "../../../shared/logging";
import { TELEMETRY_UI_NOTIFY_MIN_MS } from "./telemetryStreamConstants";
import { isTelemetryRecord, parseTelemetryMessage, telemetryFromMessage } from "./telemetryStreamParse";
import type {
  SharedTelemetryState,
  TelemetrySnapshot,
  TelemetrySubscriber,
} from "./telemetryStreamTypes";
import { telemetryWebSocketUrl } from "./telemetryStreamUrl";

export const sharedTelemetryState: SharedTelemetryState = {
  telemetry: null,
  isConnected: false,
  error: null,
  reconnectAttempt: 0,
  lastPacketAt: null,
};

export const telemetrySubscribers = new Set<TelemetrySubscriber>();

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let pingTimer: number | null = null;
let closeTimer: number | null = null;
let notifyRaf: number | null = null;
let notifyThrottleTimer: number | null = null;
let lastNotifyAt = 0;
let pendingTelemetryCallback: TelemetrySnapshot | null = null;
let attempt = 0;
let explicitlyClosed = false;
let websocketFactory: ((url: string) => WebSocket) | null = null;

export function setSharedTelemetryWebSocketFactory(
  factory: ((url: string) => WebSocket) | null,
) {
  websocketFactory = factory;
}

export function resetSharedTelemetryAttempt() {
  attempt = 0;
}

function flushNotify() {
  lastNotifyAt = Date.now();
  if (notifyRaf != null) {
    window.cancelAnimationFrame(notifyRaf);
    notifyRaf = null;
  }
  if (notifyThrottleTimer != null) {
    window.clearTimeout(notifyThrottleTimer);
    notifyThrottleTimer = null;
  }
  const telemetryCb = pendingTelemetryCallback;
  pendingTelemetryCallback = null;
  if (telemetryCb) {
    telemetrySubscribers.forEach((subscriber) => subscriber.onTelemetry?.(telemetryCb));
  }
  notifySharedTelemetrySubscribers();
}

function scheduleNotify() {
  const elapsed = Date.now() - lastNotifyAt;
  if (elapsed >= TELEMETRY_UI_NOTIFY_MIN_MS) {
    if (notifyRaf != null) return;
    notifyRaf = window.requestAnimationFrame(() => {
      notifyRaf = null;
      flushNotify();
    });
    return;
  }
  if (notifyThrottleTimer != null) return;
  notifyThrottleTimer = window.setTimeout(() => {
    notifyThrottleTimer = null;
    flushNotify();
  }, TELEMETRY_UI_NOTIFY_MIN_MS - elapsed);
}

export function notifySharedTelemetrySubscribers() {
  telemetrySubscribers.forEach((subscriber) =>
    subscriber.onState({ ...sharedTelemetryState }),
  );
}

function clearTimers() {
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  if (pingTimer) window.clearInterval(pingTimer);
  if (closeTimer) window.clearTimeout(closeTimer);
  reconnectTimer = null;
  pingTimer = null;
  closeTimer = null;
}

export function connectSharedTelemetry() {
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
  socket = websocketFactory?.(telemetryWebSocketUrl()) ?? new globalThis.WebSocket(telemetryWebSocketUrl());

  socket.onopen = () => {
    sharedTelemetryState.isConnected = true;
    sharedTelemetryState.error = null;
    sharedTelemetryState.reconnectAttempt = 0;
    attempt = 0;
    emitAppLog({
      level: "info",
      source: "websocket",
      message: "Telemetry websocket connected",
    });
    scheduleNotify();
    if (pingTimer) window.clearInterval(pingTimer);
    pingTimer = window.setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  };

  socket.onmessage = async (event) => {
    const msg = await parseTelemetryMessage(event.data);
    if (msg === "pong" || (isTelemetryRecord(msg) && msg.type === "pong")) return;
    if (isTelemetryRecord(msg) && msg.type === "app_log" && msg.data) {
      emitAppLog(msg.data as AppLogEvent, { mirrorToConsole: false });
      telemetrySubscribers.forEach((subscriber) => subscriber.onMessage?.(msg));
      return;
    }
    telemetrySubscribers.forEach((subscriber) => subscriber.onMessage?.(msg));
    const telemetry = telemetryFromMessage(msg);
    if (telemetry) {
      sharedTelemetryState.telemetry = telemetry;
      sharedTelemetryState.lastPacketAt = Date.now();
      pendingTelemetryCallback = telemetry;
      scheduleNotify();
    }
  };

  socket.onerror = () => {
    sharedTelemetryState.error = "WebSocket connection error";
    emitAppLog({
      level: "error",
      source: "websocket",
      message: "Telemetry websocket connection error",
      details: { attempt: currentAttempt },
    });
    scheduleNotify();
  };

  socket.onclose = (event) => {
    socket = null;
    sharedTelemetryState.isConnected = false;
    scheduleNotify();
    if (pingTimer) window.clearInterval(pingTimer);
    pingTimer = null;
    if (explicitlyClosed || event.code === 1000 || event.code === 1008) return;
    if (telemetrySubscribers.size === 0) return;
    const nextAttempt = currentAttempt + 1;
    if (nextAttempt > 10) {
      sharedTelemetryState.error = "Max reconnection attempts reached";
      emitAppLog({
        level: "critical",
        source: "websocket",
        message: "Telemetry websocket could not reconnect",
        details: { close_code: event.code, close_reason: event.reason },
      });
      scheduleNotify();
      return;
    }
    sharedTelemetryState.reconnectAttempt = nextAttempt;
    scheduleNotify();
    const delay = Math.min(
      1000 * Math.pow(2, Math.max(0, nextAttempt - 1)),
      30000,
    );
    reconnectTimer = window.setTimeout(connectSharedTelemetry, delay);
  };
}

export function disconnectSharedTelemetry({ clearTelemetry = false } = {}) {
  clearTimers();
  if (notifyRaf != null) {
    window.cancelAnimationFrame(notifyRaf);
    notifyRaf = null;
  }
  if (notifyThrottleTimer != null) {
    window.clearTimeout(notifyThrottleTimer);
    notifyThrottleTimer = null;
  }
  pendingTelemetryCallback = null;
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
  sharedTelemetryState.isConnected = false;
  sharedTelemetryState.reconnectAttempt = 0;
  if (clearTelemetry) {
    sharedTelemetryState.telemetry = null;
    sharedTelemetryState.error = null;
    sharedTelemetryState.lastPacketAt = null;
  }
  notifySharedTelemetrySubscribers();
}

export function disconnectSharedTelemetryWhenIdle() {
  if (closeTimer) window.clearTimeout(closeTimer);
  closeTimer = window.setTimeout(() => {
    closeTimer = null;
    if (telemetrySubscribers.size === 0) disconnectSharedTelemetry();
  }, 250);
}
