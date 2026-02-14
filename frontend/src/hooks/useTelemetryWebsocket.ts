// useTelemetryWebsocket.ts (FIXED VERSION)
import { useState, useEffect, useCallback, useRef } from "react";
import { getToken } from "../auth";

type TelemetryWebSocketOptions = {
  enabled?: boolean;
  onTelemetry?: (data: any) => void;
};

export const useTelemetryWebSocket = (options: TelemetryWebSocketOptions = {}) => {
  const enabled = options.enabled ?? false;
  const [telemetry, setTelemetry] = useState<any | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const shouldReconnectRef = useRef(true);
  const reconnectTimerRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const connectionAttemptRef = useRef(0);
  const onTelemetryRef = useRef<TelemetryWebSocketOptions["onTelemetry"]>(
    options.onTelemetry,
  );

  useEffect(() => {
    onTelemetryRef.current = options.onTelemetry;
  }, [options.onTelemetry]);

  // Helper to parse incoming messages
  const parseMessage = async (data: any): Promise<any> => {
    try {
      if (typeof data === "string") {
        return JSON.parse(data);
      }
      if (data instanceof Blob) {
        const text = await data.text();
        return JSON.parse(text);
      }
      if (data instanceof ArrayBuffer) {
        const text = new TextDecoder("utf-8").decode(data);
        return JSON.parse(text);
      }
      return null;
    } catch (e) {
      return data;
    }
  };

  const cleanupWebSocket = useCallback(
    (opts?: { clearTelemetry?: boolean; disableReconnect?: boolean }) => {
      const clearTelemetry = opts?.clearTelemetry ?? true;
      const disableReconnect = opts?.disableReconnect ?? true;

      if (disableReconnect) {
        shouldReconnectRef.current = false;
      }

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      if (wsRef.current) {
        // Remove all event listeners to prevent memory leaks
        wsRef.current.onopen = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;

        if (
          wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING
        ) {
          wsRef.current.close(1000, "Manual disconnect");
        }
        wsRef.current = null;
      }

      setIsConnected(false);
      if (clearTelemetry) {
        setTelemetry(null);
        setError(null);
      }
      setReconnectAttempt(0);
    },
    [],
  );

  const disconnectWebSocket = useCallback(() => {
    console.log("🛑 Disconnecting WebSocket...");
    cleanupWebSocket();
  }, [cleanupWebSocket]);

  const connectWebSocket = useCallback(() => {
    if (!enabled || !mountedRef.current) return;

    // Clear existing connection/timers but keep telemetry visible during reconnects
    cleanupWebSocket({ clearTelemetry: false, disableReconnect: false });

    shouldReconnectRef.current = true;
    connectionAttemptRef.current += 1;
    const currentAttempt = connectionAttemptRef.current;

    const token = getToken();
    if (!token) {
      setError("Not authenticated");
      return;
    }

    const apiBaseRaw = import.meta.env.VITE_API_BASE_URL as string | undefined;
    const apiBase = (apiBaseRaw?.trim() || "http://localhost:8000").replace(/\/$/, "");

    const wsUrl = apiBase.replace(/^http/, "ws") + `/ws/telemetry?token=${encodeURIComponent(token)}`;

    console.log(`🔗 Connecting to WebSocket (attempt ${connectionAttemptRef.current})`);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        console.log(`✅ WebSocket connected (attempt ${currentAttempt})`);
        setIsConnected(true);
        setError(null);
        setReconnectAttempt(0);

        // Setup ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }
        pingIntervalRef.current = window.setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: "ping" }));
          }
        }, 30000);
      };

      ws.onmessage = async (event) => {
        if (!mountedRef.current || ws !== wsRef.current) return;

        try {
          const msg = await parseMessage(event.data);

          // Handle pong responses
          if (msg === "pong" || msg?.type === "pong") {
            return;
          }

          // Handle telemetry data
          let telemetryData = msg;
          if (msg?.type === "telemetry" && msg.data) {
            telemetryData = msg.data;
          }

          if (telemetryData) {
            setTelemetry(telemetryData);
            if (onTelemetryRef.current) {
              onTelemetryRef.current(telemetryData);
            }
          }
        } catch (e) {
          console.warn("Failed to parse WebSocket message:", e);
        }
      };

      ws.onerror = (event) => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        console.error(`❌ WebSocket error (attempt ${currentAttempt})`, event);
        setError("WebSocket connection error");
      };

      ws.onclose = (ev) => {
        if (!mountedRef.current || ws !== wsRef.current) return;

        console.log(`🔌 WebSocket closed (code: ${ev.code}, reason: ${ev.reason})`);
        setIsConnected(false);

        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Don't reconnect on manual disconnect or auth errors
        if (!shouldReconnectRef.current || ev.code === 1000 || ev.code === 1008) {
          return;
        }

        // Exponential backoff reconnect
        const maxAttempts = 10;
        if (currentAttempt >= maxAttempts) {
          setError("Max reconnection attempts reached");
          return;
        }

        const delay = Math.min(1000 * Math.pow(2, currentAttempt - 1), 30000);
        setReconnectAttempt(currentAttempt);

        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current);
        }

        reconnectTimerRef.current = window.setTimeout(() => {
          if (mountedRef.current && shouldReconnectRef.current) {
            connectWebSocket();
          }
        }, delay);
      };
    } catch (error) {
      console.error(`❌ Failed to create WebSocket: ${error}`);
    }
  }, [enabled, cleanupWebSocket]);



  // Initial connection effect
  useEffect(() => {
    mountedRef.current = true;

    let timer: number | null = null;

    if (enabled) {
      timer = window.setTimeout(connectWebSocket, 100);
    } else {
      disconnectWebSocket();
    }

    return () => {
      if (timer) window.clearTimeout(timer);
      mountedRef.current = false;
      disconnectWebSocket();
    };
  }, [enabled, connectWebSocket, disconnectWebSocket]);


  const manualReconnect = useCallback(() => {
    if (!enabled) return;
    console.log("🔄 Manual reconnect requested");
    connectionAttemptRef.current = 0; // Reset attempt counter
    disconnectWebSocket();
    setTimeout(() => {
      if (mountedRef.current) {
        connectWebSocket();
      }
    }, 500);
  }, [enabled, disconnectWebSocket, connectWebSocket]);

  return {
    telemetry,
    isConnected,
    error,
    reconnect: manualReconnect,
    disconnect: disconnectWebSocket,
    reconnectAttempt,
  };
};

export default useTelemetryWebSocket;
