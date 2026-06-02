import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { missionKeys } from "../../../app/config/queryKeys";
import { getSessionMarker } from "../../session";
import { fetchFlightStatus } from "../api/missionsApi";
import type { MissionLifecycleEvent, MissionStatusPayload } from "../types";

export function useMissionStatusPolling<TStatus extends MissionStatusPayload>({
  enabled = true,
  pollMs = 5000,
  lifecycleMessage,
  onError,
}: {
  enabled?: boolean;
  pollMs?: number;
  lifecycleMessage?: MissionLifecycleEvent | null;
  onError?: (message: string) => void;
}) {
  const [activeFlightId, setActiveFlightId] = useState<string | null>(null);
  const activeFlightIdRef = useRef<string | null>(null);
  const missionStartAtRef = useRef<number | null>(null);

  activeFlightIdRef.current = activeFlightId;

  const statusQuery = useQuery({
    queryKey: missionKeys.flightStatus(),
    queryFn: () => fetchFlightStatus<TStatus>(getSessionMarker()),
    enabled: enabled && Boolean(getSessionMarker()),
    refetchInterval: () => (document.hidden ? Math.max(10_000, pollMs * 4) : pollMs),
    refetchIntervalInBackground: false,
    staleTime: 3_000,
    retry: false,
  });

  useEffect(() => {
    if (!statusQuery.error || !onError) return;
    onError(
      statusQuery.error instanceof Error
        ? `Flight status fetch failed: ${statusQuery.error.message}`
        : "Flight status fetch failed",
    );
  }, [onError, statusQuery.error]);

  const applyFlightId = useCallback((flightId: string | null) => {
    if (!flightId) {
      const graceMs = 30_000;
      const startedAt = missionStartAtRef.current ?? 0;
      const withinGrace = startedAt > 0 && Date.now() - startedAt < graceMs;
      if (!withinGrace) setActiveFlightId(null);
      return;
    }
    if (flightId !== activeFlightIdRef.current) {
      setActiveFlightId(flightId);
      missionStartAtRef.current = Date.now();
    }
  }, []);

  useEffect(() => {
    const next = statusQuery.data;
    if (!next) return;
    const flightId = (next as MissionStatusPayload).flight_id ?? null;
    applyFlightId(flightId);
  }, [applyFlightId, statusQuery.data]);

  useEffect(() => {
    if (!lifecycleMessage || lifecycleMessage.type !== "mission_lifecycle") return;
    const data = lifecycleMessage.data;
    if (!data) return;

    const flightId = data.mission?.client_flight_id ?? data.mission_runtime_id ?? null;
    if (flightId) {
      applyFlightId(flightId);
      return;
    }

    const state = data.payload?.state ?? "";
    const terminalStates = new Set(["completed", "aborted", "failed"]);
    if (terminalStates.has(state)) {
      const graceMs = 30_000;
      const startedAt = missionStartAtRef.current ?? 0;
      const withinGrace = startedAt > 0 && Date.now() - startedAt < graceMs;
      if (!withinGrace) setActiveFlightId(null);
    }
  }, [applyFlightId, lifecycleMessage]);

  return {
    status: statusQuery.data ?? null,
    activeFlightId,
    isLoading: statusQuery.isLoading,
    refetch: statusQuery.refetch,
  };
}
