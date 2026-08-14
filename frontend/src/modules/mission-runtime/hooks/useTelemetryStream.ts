import { useCallback, useEffect, useRef, useState } from "react";
import {
  connectSharedTelemetry,
  disconnectSharedTelemetry,
  disconnectSharedTelemetryWhenIdle,
  resetSharedTelemetryAttempt,
  setSharedTelemetryWebSocketFactory,
  sharedTelemetryState,
  telemetrySubscribers,
} from "../realtime/sharedTelemetryConnection";
import { TELEMETRY_UI_NOTIFY_MIN_MS } from "../realtime/telemetryStreamConstants";
import type {
  SharedTelemetryState,
  TelemetrySubscriber,
  TelemetryWebSocketOptions,
} from "../realtime/telemetryStreamTypes";

export { TELEMETRY_UI_NOTIFY_MIN_MS };

export function setTelemetryWebSocketFactoryForTests(
  factory: ((url: string) => WebSocket) | null,
) {
  setSharedTelemetryWebSocketFactory(factory);
  if (factory === null) {
    telemetrySubscribers.clear();
    disconnectSharedTelemetry({ clearTelemetry: true });
  }
}

export function useTelemetryStream(options: TelemetryWebSocketOptions = {}) {
  const enabled = options.enabled ?? false;
  const [snapshot, setSnapshot] = useState<SharedTelemetryState>({ ...sharedTelemetryState });
  const subscriberRef = useRef<TelemetrySubscriber>({
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
    telemetrySubscribers.add(subscriber);
    subscriber.onState({ ...sharedTelemetryState });
    connectSharedTelemetry();
    return () => {
      telemetrySubscribers.delete(subscriber);
      if (telemetrySubscribers.size === 0) disconnectSharedTelemetryWhenIdle();
    };
  }, [enabled]);

  const reconnect = useCallback(() => {
    if (!enabled) return;
    resetSharedTelemetryAttempt();
    disconnectSharedTelemetry({ clearTelemetry: false });
    connectSharedTelemetry();
  }, [enabled]);

  const disconnect = useCallback(() => {
    if (subscriberRef.current) telemetrySubscribers.delete(subscriberRef.current);
    if (telemetrySubscribers.size === 0) disconnectSharedTelemetry({ clearTelemetry: true });
  }, []);

  return {
    telemetry: snapshot.telemetry,
    isConnected: snapshot.isConnected,
    error: snapshot.error,
    reconnect,
    disconnect,
    reconnectAttempt: snapshot.reconnectAttempt,
    lastPacketAt: snapshot.lastPacketAt,
  };
}

export const useTelemetryWebSocket = useTelemetryStream;
export default useTelemetryStream;
