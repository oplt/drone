import { useEffect, useMemo, useState } from "react";
import { useTelemetryStream } from "./useTelemetryStream";

export type TelemetryLinkPhase = "live" | "stale" | "reconnecting" | "offline";

export type TelemetryLinkStatus = {
  phase: TelemetryLinkPhase;
  label: string;
  color: "success" | "warning" | "error" | "default";
  ageSec: number | null;
  isConnected: boolean;
  reconnectAttempt: number;
};

const STALE_AFTER_MS = 8_000;

/**
 * Operator-facing link status derived from the shared telemetry websocket.
 * Never reports "live" without an open socket and a recent packet.
 */
export function useTelemetryLinkStatus(options: { enabled?: boolean } = {}): TelemetryLinkStatus {
  const enabled = options.enabled ?? true;
  const { isConnected, reconnectAttempt, lastPacketAt, error } = useTelemetryStream({
    enabled,
  });
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!enabled) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [enabled]);

  return useMemo(() => {
    const ageSec =
      lastPacketAt != null ? Math.max(0, Math.round((now - lastPacketAt) / 1000)) : null;
    const packetFresh =
      lastPacketAt != null && now - lastPacketAt <= STALE_AFTER_MS;

    if (!enabled) {
      return {
        phase: "offline" as const,
        label: "Telemetry off",
        color: "default" as const,
        ageSec: null,
        isConnected: false,
        reconnectAttempt: 0,
      };
    }

    if (reconnectAttempt > 0 && !isConnected) {
      return {
        phase: "reconnecting" as const,
        label: `Reconnecting (${reconnectAttempt})`,
        color: "warning" as const,
        ageSec,
        isConnected: false,
        reconnectAttempt,
      };
    }

    if (!isConnected || error) {
      return {
        phase: "offline" as const,
        label: "Telemetry offline",
        color: "error" as const,
        ageSec,
        isConnected: false,
        reconnectAttempt,
      };
    }

    if (!packetFresh) {
      return {
        phase: "stale" as const,
        label: ageSec != null ? `Telemetry stale (${ageSec}s)` : "Telemetry stale",
        color: "warning" as const,
        ageSec,
        isConnected: true,
        reconnectAttempt,
      };
    }

    return {
      phase: "live" as const,
      label: "Telemetry live",
      color: "success" as const,
      ageSec,
      isConnected: true,
      reconnectAttempt,
    };
  }, [enabled, error, isConnected, lastPacketAt, now, reconnectAttempt]);
}
