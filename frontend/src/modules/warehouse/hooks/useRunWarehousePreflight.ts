import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import {
  fetchWarehousePreflight,
  type WarehouseGoPreflight,
  type WarehousePreflightRefresh,
} from "../api/warehousePreflightApi";
import { preflightRunPollIntervalMs } from "./preflightPolling";
import { useStartWarehousePreflightRefresh } from "./useStartWarehousePreflightRefresh";
import { useWarehousePreflightRun } from "./useWarehousePreflightRun";

const DEFAULT_TIMEOUT_MS = 120000;
const TRANSIENT_FAILURE_KEYS = new Set(["stability", "telemetry_stream", "bridge"]);
const TRANSIENT_STATUSES = new Set(["WAITING", "UNKNOWN"]);

/** Backend ready_to_fly must match panel topic categories (no PASS with RGB/depth/IMU FAIL). */
export function warehousePreflightPassed(
  preflight: WarehouseGoPreflight | null,
): boolean {
  if (!preflight?.ready_to_fly) return false;
  const rgbDepthImu = preflight.categories?.rgb_depth_imu;
  const sensors = preflight.categories?.sensors;
  if (rgbDepthImu === "FAIL" || sensors === "FAIL") return false;
  const topicRows = preflight.diagnostics?.topics?.by_category ?? {};
  for (const key of ["rgb", "depth", "imu"] as const) {
    const row = topicRows[key];
    if (row && typeof row === "object" && "status" in row && row.status === "FAIL") {
      return false;
    }
  }
  return true;
}

function hasProbeInProgress(preflight: WarehouseGoPreflight): boolean {
  return preflight.blocking_reasons.some((reason) =>
    reason.toLowerCase().includes("probe in progress"),
  );
}

function refreshInProgress(preflight: WarehouseGoPreflight): boolean {
  return Boolean(
    preflight.diagnostics?.cache?.refresh_in_progress ||
      preflight.diagnostics?.timings?.refresh_in_progress ||
      preflight.diagnostics?.bridge?.health_probe_in_progress ||
      hasProbeInProgress(preflight),
  );
}

function isTerminalPreflightFailure(
  preflight: WarehouseGoPreflight,
  run?: WarehousePreflightRefresh | null,
): boolean {
  if (warehousePreflightPassed(preflight) || refreshInProgress(preflight)) return false;
  if (run && run.status !== "complete" && run.status !== "failed") return false;

  return Object.entries(preflight.categories ?? {}).some(([key, status]) => {
    if (TRANSIENT_FAILURE_KEYS.has(key)) return false;
    if (TRANSIENT_STATUSES.has(status)) return false;
    return status === "FAIL";
  });
}

/** Exported for unit tests (run polling cadence). */
export function warehousePreflightPollIntervalMs(elapsedMs: number): number | false {
  return preflightRunPollIntervalMs(elapsedMs);
}

function blockedMessage(
  preflight: WarehouseGoPreflight,
  connectWarning: string | null,
): string {
  const reason = preflight.blocking_reasons[0];
  const base = reason
    ? `Preflight blocked: ${reason}`
    : "Preflight blocked by failed checks.";
  if (
    connectWarning &&
    (!preflight.vehicle_link_ok || !preflight.telemetry_stream_ok)
  ) {
    return `${base} ${connectWarning}`;
  }
  return base;
}

function timeoutMessage(
  preflight: WarehouseGoPreflight | null,
  connectWarning: string | null,
): string {
  if (connectWarning && preflight && !preflight.telemetry_stream_ok) {
    return connectWarning;
  }

  const stability = preflight?.diagnostics?.stability;
  const remainingMs =
    typeof stability?.remaining_ms === "number"
      ? stability.remaining_ms
      : Math.max(
          0,
          (preflight?.perception_required_stable_ms ?? 0) -
            (preflight?.perception_stable_for_ms ?? 0),
        );
  const reason = preflight?.blocking_reasons?.[0];

  if (remainingMs > 0) {
    const seconds = Math.ceil(remainingMs / 1000);
    return reason
      ? `${reason}. Stability needs about ${seconds}s more of healthy samples.`
      : `Waiting for perception to remain stable for ${seconds}s more.`;
  }

  return reason
    ? `Preflight still not ready: ${reason}`
    : "Preflight checks did not become ready before the timeout.";
}

function isRunTerminal(run: WarehousePreflightRefresh | null | undefined): boolean {
  return run?.status === "complete" || run?.status === "failed";
}

export function useRunWarehousePreflight(token: string | null) {
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [result, setResult] = useState<WarehouseGoPreflight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);
  const activeRunRef = useRef<Promise<WarehouseGoPreflight | null> | null>(null);
  const deadlineRef = useRef<number | null>(null);
  const connectWarningRef = useRef<string | null>(null);
  const resolveRunRef = useRef<((value: WarehouseGoPreflight | null) => void) | null>(
    null,
  );
  const handledRunIdRef = useRef<string | null>(null);

  const startRefresh = useStartWarehousePreflightRefresh(token);
  const runQuery = useWarehousePreflightRun(token, activeRunId, {
    enabled: running && Boolean(activeRunId),
  });

  const finishRun = useCallback(
    (snapshot: WarehouseGoPreflight | null, runError: string | null = null) => {
      setRunning(false);
      setActiveRunId(null);
      deadlineRef.current = null;
      setError(runError);
      resolveRunRef.current?.(snapshot);
      resolveRunRef.current = null;
      activeRunRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!running || !runQuery.data) return;

    const run = runQuery.data;
    if (run.status === "running") {
      if (run.snapshot) setResult(run.snapshot);
      return;
    }
    if (handledRunIdRef.current === run.run_id) return;
    handledRunIdRef.current = run.run_id;

    void (async () => {
      let snapshot = run.snapshot ?? null;
      if (!snapshot && token) {
        snapshot = await fetchWarehousePreflight(token, {
          missionLoaded: run.mission_loaded,
        }).catch(() => null);
      }
      if (snapshot) {
        setResult(snapshot);
        void queryClient.invalidateQueries({
          queryKey: ["warehouse-preflight", token],
        });
      }

      if (run.status === "failed") {
        finishRun(
          snapshot,
          run.error ??
            (snapshot
              ? blockedMessage(snapshot, connectWarningRef.current)
              : "Preflight refresh failed."),
        );
        return;
      }

      if (snapshot && warehousePreflightPassed(snapshot)) {
        finishRun(snapshot, null);
        return;
      }

      if (snapshot && isTerminalPreflightFailure(snapshot, run)) {
        finishRun(snapshot, blockedMessage(snapshot, connectWarningRef.current));
        return;
      }

      finishRun(snapshot, null);
    })();
  }, [finishRun, queryClient, runQuery.data, running, token]);

  useEffect(() => {
    if (!running || !deadlineRef.current) return;

    const remaining = Math.max(0, deadlineRef.current - Date.now());
    const timeoutId = window.setTimeout(() => {
      if (!running) return;
      abortRef.current = true;
      setError(timeoutMessage(result, connectWarningRef.current));
      finishRun(result);
    }, remaining);

    return () => window.clearTimeout(timeoutId);
  }, [finishRun, result, running, activeRunId]);

  const reset = useCallback(() => {
    abortRef.current = true;
    finishRun(null);
    setResult(null);
    setError(null);
  }, [finishRun]);

  const runChecks = useCallback(
    async (options?: { missionLoaded?: boolean; timeoutMs?: number }) => {
      if (activeRunRef.current) {
        return activeRunRef.current;
      }
      if (startRefresh.isPending) {
        return null;
      }
      if (!token) {
        setError("Authentication required to run preflight checks.");
        return null;
      }

      abortRef.current = false;
      handledRunIdRef.current = null;
      setRunning(true);
      setError(null);
      connectWarningRef.current = null;
      deadlineRef.current = Date.now() + (options?.timeoutMs ?? DEFAULT_TIMEOUT_MS);

      void connectDroneTelemetry(token, "warehouse_scan", "indoor_local").catch((err) => {
        connectWarningRef.current =
          err instanceof Error
            ? `Drone telemetry connect failed: ${err.message}`
            : "Drone telemetry connect failed.";
      });

      const runPromise = (async () => {
        try {
          const run = await startRefresh.mutateAsync({
            missionLoaded: options?.missionLoaded,
            deep: true,
            force: false,
          });
          if (!run.run_id || abortRef.current) {
            finishRun(null, "Preflight refresh did not return a run id.");
            return null;
          }

          setActiveRunId(run.run_id);

          return await new Promise<WarehouseGoPreflight | null>((resolve) => {
            resolveRunRef.current = resolve;
            if (isRunTerminal(run)) {
              void (async () => {
                handledRunIdRef.current = run.run_id;
                let snapshot = run.snapshot ?? null;
                if (!snapshot) {
                  snapshot = await fetchWarehousePreflight(token, {
                    missionLoaded: options?.missionLoaded,
                  }).catch(() => null);
                }
                if (snapshot) setResult(snapshot);
                const terminalError =
                  run.status === "failed"
                    ? run.error ??
                      (snapshot
                        ? blockedMessage(snapshot, connectWarningRef.current)
                        : "Preflight refresh failed.")
                    : snapshot && isTerminalPreflightFailure(snapshot, run)
                      ? blockedMessage(snapshot, connectWarningRef.current)
                      : null;
                finishRun(snapshot, terminalError);
                resolve(snapshot);
              })();
            }
          });
        } catch (err) {
          const message =
            err instanceof Error ? err.message : "Preflight refresh failed.";
          finishRun(null, message);
          return null;
        }
      })();

      activeRunRef.current = runPromise;
      return runPromise;
    },
    [finishRun, startRefresh, token],
  );

  return {
    running,
    result,
    error,
    runChecks,
    reset,
    passed: warehousePreflightPassed(result),
    activeRunId,
  };
}
