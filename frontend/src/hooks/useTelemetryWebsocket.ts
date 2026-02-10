import { useState, useEffect, useCallback, useRef } from 'react';

export interface TelemetryData {
  position: {
    lat: number;
    lon: number;
    alt: number;
    relative_alt: number;
  };
  attitude?: {
    roll: number;
    pitch: number;
    yaw: number;
    rollspeed: number;
    pitchspeed: number;
    yawspeed: number;
  };
  battery: {
    voltage: number;
    current: number;
    remaining: number;
    temperature?: number;
  };
  status: {
    groundspeed: number;
    airspeed?: number;
    heading: number;
    throttle?: number;
    alt?: number;
    climb?: number;
  };
  gps?: {
    fix_type: number;
    satellites_visible: number;
    hdop: number;
    vdop: number;
  };
  system?: {
    voltage_battery: number;
    current_battery: number;
    battery_remaining: number;
    load: number;
  };
  mode: string;
  armed: boolean;
  timestamp: number;
}

// ALSO MAKE SURE THE HOOK IS EXPORTED
export const useTelemetryWebSocket = () => {
  const [telemetry, setTelemetry] = useState<any | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const shouldReconnectRef = useRef(true);
  const reconnectTimerRef = useRef<number | null>(null);

  const latestRef = useRef<any | null>(null);
  const rafRef = useRef<number | null>(null);

  const connectWebSocket = useCallback(() => {
      shouldReconnectRef.current = true;
      if (wsRef.current) wsRef.current.close();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//localhost:8000/ws/telemetry/public`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
        setIsConnected(true);
        setError(null);
    };

    const rafRef = useRef<number | null>(null);

    ws.onmessage = (event) => {
          try {
            // backend patch sends TEXT JSON
            const msg = JSON.parse(event.data);
            if (msg?.type === "telemetry") {
              latestRef.current = msg.data;

              if (rafRef.current == null) {
                rafRef.current = requestAnimationFrame(() => {
                  rafRef.current = null;
                  setTelemetry(latestRef.current);
                });
              }
            }
          } catch (e) {
            // optional: console.warn("Bad WS message", e);
          }
        };

      ws.onerror = () => {
          setError("WebSocket connection error");
          setIsConnected(false);
      };

      ws.onclose = () => {
            setIsConnected(false);
            if (!shouldReconnectRef.current) return;

            if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = window.setTimeout(connectWebSocket, 1000);
          };
        }, []);

        const disconnectWebSocket = useCallback(() => {
          shouldReconnectRef.current = false;
          if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
          wsRef.current?.close();
          wsRef.current = null;
        }, []);

  useEffect(() => {
      connectWebSocket();
      return () => disconnectWebSocket();
    }, [connectWebSocket, disconnectWebSocket]);

    return { telemetry, isConnected, error, reconnect: connectWebSocket, disconnect: disconnectWebSocket };
  };

  export default useTelemetryWebSocket;