import { useCallback, useRef, useState } from "react";
import { useInterval } from "./useInterval";

export function useMissionStatusPolling<TStatus>({
  apiBase,
  getToken,
  onError,
  enabled = true,
  intervalMs = 5000,
}: {
  apiBase: string;
  getToken: () => string | null;
  onError: (msg: string) => void;
  enabled?: boolean;
  intervalMs?: number;
}) {
  const [status, setStatus] = useState<TStatus | null>(null);
  const [activeFlightId, setActiveFlightId] = useState<string | null>(null);

  const activeFlightIdRef = useRef<string | null>(null);
  activeFlightIdRef.current = activeFlightId;

  const missionStartAtRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    try {
      const res = await fetch(`${apiBase}/tasks/flight/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const next = (await res.json()) as any as TStatus;
      setStatus(next);

      const flightId = (next as any)?.flight_id ?? null;

      if (!flightId) {
        const graceMs = 30000;
        const startedAt = missionStartAtRef.current ?? 0;
        const withinGrace = startedAt > 0 && Date.now() - startedAt < graceMs;
        if (!withinGrace) setActiveFlightId(null);
        return;
      }

      if (flightId !== activeFlightIdRef.current) {
        setActiveFlightId(flightId);
        missionStartAtRef.current = Date.now();
      }
    } catch (e) {
      onError(`Flight status polling failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  }, [apiBase, getToken, onError]);

  useInterval(poll, enabled ? intervalMs : null);

  return { status, activeFlightId, poll };
}