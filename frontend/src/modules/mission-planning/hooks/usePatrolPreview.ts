import { useCallback, useEffect, useRef, useState } from "react";
import { getSessionMarker } from "../../session";
import { fetchPatrolPreview } from "../api/planningApi";
import type { GridPreviewStats, GridPreviewWaypoint } from "../types";

const DEFAULT_DEBOUNCE_MS = 250;

export function usePatrolPreview({
  enabled = true,
  requestBody,
  debounceMs = DEFAULT_DEBOUNCE_MS,
}: {
  enabled?: boolean;
  requestBody: Record<string, unknown> | null;
  debounceMs?: number;
}) {
  const [waypoints, setWaypoints] = useState<GridPreviewWaypoint[] | null>(null);
  const [workLegMask, setWorkLegMask] = useState<boolean[] | null>(null);
  const [stats, setStats] = useState<GridPreviewStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const runPreview = useCallback(
    async (signal: AbortSignal) => {
      if (!enabled || !requestBody) {
        setWaypoints(null);
        setWorkLegMask(null);
        setStats(null);
        setError(null);
        setLoading(false);
        return;
      }
      const token = getSessionMarker();
      if (!token) return;

      setLoading(true);
      try {
        const data = await fetchPatrolPreview(requestBody, token, signal);
        if (signal.aborted) return;
        setWaypoints(data.waypoints ?? []);
        setWorkLegMask(data.work_leg_mask ?? null);
        setStats(data.stats ?? null);
        setError(null);
      } catch (previewError) {
        if (signal.aborted) return;
        setWaypoints(null);
        setWorkLegMask(null);
        setStats(null);
        setError(
          previewError instanceof Error
            ? previewError.message
            : "Patrol preview failed. Please try again.",
        );
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [enabled, requestBody],
  );

  useEffect(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timer = window.setTimeout(() => {
      void runPreview(controller.signal);
    }, debounceMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
      if (abortRef.current === controller) abortRef.current = null;
    };
  }, [debounceMs, runPreview]);

  return { waypoints, workLegMask, stats, error, loading };
}
