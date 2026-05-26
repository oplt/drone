import { useCallback, useEffect, useRef, useState } from "react";
import { getSessionMarker } from "../../session";
import type { LonLat } from "../../fields/types";
import { fetchGridPreview } from "../api/planningApi";
import type { GridParams, GridPreviewStats, GridPreviewWaypoint } from "../types";

const DEFAULT_DEBOUNCE_MS = 250;

export function useGridPreview({
  enabled = true,
  fieldBorder,
  gridParams,
  debounceMs = DEFAULT_DEBOUNCE_MS,
}: {
  enabled?: boolean;
  fieldBorder: LonLat[] | null;
  gridParams: GridParams;
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
      if (!enabled) {
        setLoading(false);
        return;
      }
      if (!fieldBorder || fieldBorder.length < 3) {
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
        const data = await fetchGridPreview(
          { field_polygon_lonlat: fieldBorder, gridParams },
          token,
          signal,
        );
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
            : "Grid preview failed. Please try again.",
        );
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [enabled, fieldBorder, gridParams],
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

  return {
    waypoints,
    workLegMask,
    stats,
    error,
    loading,
    refresh: () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      void runPreview(controller.signal);
    },
  };
}
