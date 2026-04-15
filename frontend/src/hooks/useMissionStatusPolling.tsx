import { useCallback, useEffect, useRef, useState } from "react";

export function useMissionStatusPolling<TStatus>({
  apiBase,
  getToken,
  onError,
  enabled = true,
  lifecycleMessage,
}: {
  apiBase: string;
  getToken: () => string | null;
  onError: (msg: string) => void;
  enabled?: boolean;
  lifecycleMessage?: any;
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
      onError(`Flight status fetch failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  }, [apiBase, getToken, onError]);

  // Poll on mount and then every 3s while enabled
  useEffect(() => {
    if (!enabled) return;
    poll();
    const id = window.setInterval(poll, 3000);
    return () => window.clearInterval(id);
  }, [enabled, poll]);

  // Update state from WebSocket mission_lifecycle messages
  useEffect(() => {
    if (!lifecycleMessage || lifecycleMessage.type !== "mission_lifecycle") return;
    const data = lifecycleMessage.data;
    if (!data) return;

    // Extract flight identifier from the lifecycle envelope mission context
    const flightId: string | null =
      data.mission?.client_flight_id ?? data.mission_runtime_id ?? null;

    if (flightId) {
      if (flightId !== activeFlightIdRef.current) {
        setActiveFlightId(flightId);
        missionStartAtRef.current = Date.now();
      }

      setStatus((prev) => {
        if (!prev) return prev;
        const prevLifecycle = (prev as any).mission_lifecycle ?? {};
        const updatedAt = data.emitted_at
          ? new Date(data.emitted_at).getTime() / 1000
          : prevLifecycle.updated_at;
        return {
          ...prev,
          mission_lifecycle: {
            ...prevLifecycle,
            flight_id: flightId,
            state: data.payload?.state ?? prevLifecycle.state,
            updated_at: updatedAt,
          },
        } as TStatus;
      });
    } else {
      // Terminal state with no flight — clear active flight after grace period
      const state: string = data.payload?.state ?? "";
      const terminalStates = new Set(["completed", "aborted", "failed"]);
      if (terminalStates.has(state)) {
        const graceMs = 30000;
        const startedAt = missionStartAtRef.current ?? 0;
        const withinGrace = startedAt > 0 && Date.now() - startedAt < graceMs;
        if (!withinGrace) setActiveFlightId(null);
      }
    }
  }, [lifecycleMessage]);

  return { status, activeFlightId, poll };
}
