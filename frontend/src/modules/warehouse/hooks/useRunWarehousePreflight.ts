import { useCallback, useRef, useState } from "react";
import { connectDroneTelemetry } from "../../mission-runtime/api/telemetryConnectApi";
import {
  fetchWarehousePreflight,
  type WarehouseGoPreflight,
} from "../api/warehousePreflightApi";

const POLL_MS = 1000;
const POLL_MS_MID = 600;
const POLL_MS_FAST = 350;
const DEFAULT_TIMEOUT_MS = 120000;
const DEEP_REFRESH_MS = 30000;
const TRANSIENT_FAILURE_KEYS = new Set(["stability"]);
const TRANSIENT_STATUSES = new Set(["WAITING", "UNKNOWN"]);

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function hasProbeInProgress(preflight: WarehouseGoPreflight): boolean {
  return preflight.blocking_reasons.some((reason) =>
    reason.toLowerCase().includes("probe in progress"),
  );
}

function isTerminalPreflightFailure(preflight: WarehouseGoPreflight): boolean {
  if (preflight.ready_to_fly || hasProbeInProgress(preflight)) return false;

  return Object.entries(preflight.categories ?? {}).some(([key, status]) => {
    if (TRANSIENT_FAILURE_KEYS.has(key)) return false;
    if (TRANSIENT_STATUSES.has(status)) return false;
    return status === "FAIL";
  });
}

/** Exported for unit tests (adaptive poll cadence). */
export function warehousePreflightPollIntervalMs(
  preflight: WarehouseGoPreflight | null,
): number {
  return pollIntervalMs(preflight);
}

function pollIntervalMs(preflight: WarehouseGoPreflight | null): number {
  if (!preflight) return POLL_MS;

  const remaining =
    preflight.diagnostics?.stability?.remaining_ms ??
    Math.max(
      0,
      (preflight.perception_required_stable_ms ?? 0) -
        (preflight.perception_stable_for_ms ?? 0),
    );

  if (remaining <= 2500) return POLL_MS_FAST;
  if (remaining <= 5000) return POLL_MS_MID;

  const required = preflight.perception_required_stable_ms ?? 0;
  const stable = preflight.perception_stable_for_ms ?? 0;
  if (required > 0 && stable >= required * 0.5) return POLL_MS_MID;

  if (
    preflight.categories?.bridge === "WAITING" ||
    preflight.categories?.stability === "WAITING" ||
    preflight.warehouse_bridge_state === "starting"
  ) {
    return POLL_MS;
  }

  return POLL_MS;
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

export function useRunWarehousePreflight(token: string | null) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<WarehouseGoPreflight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);

  const reset = useCallback(() => {
    abortRef.current = true;
    setRunning(false);
    setResult(null);
    setError(null);
  }, []);

  const runChecks = useCallback(
    async (options?: { missionLoaded?: boolean; timeoutMs?: number }) => {
      if (!token) {
        setError("Authentication required to run preflight checks.");
        return null;
      }

      abortRef.current = false;
      setRunning(true);
      setError(null);

      const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
      const deadline = Date.now() + timeoutMs;
      let latest: WarehouseGoPreflight | null = null;
      let connectWarning: string | null = null;

      const connectPromise = connectDroneTelemetry(token).catch((err) => {
        connectWarning =
          err instanceof Error
            ? `Drone telemetry connect failed: ${err.message}`
            : "Drone telemetry connect failed.";
      });

      try {
        let nextDeepRefreshAt = Date.now();
        let pollIndex = 0;

        while (!abortRef.current && Date.now() < deadline) {
          const now = Date.now();
          const useDeep = pollIndex === 0 || now >= nextDeepRefreshAt;
          if (useDeep) nextDeepRefreshAt = now + DEEP_REFRESH_MS;

          const fetchSnapshot = () =>
            fetchWarehousePreflight(token, {
              missionLoaded: options?.missionLoaded,
              deep: useDeep,
            });

          const snapshot =
            pollIndex === 0
              ? await Promise.all([connectPromise, fetchSnapshot()]).then(
                  ([, value]) => value,
                )
              : await fetchSnapshot();
          pollIndex += 1;

          latest = snapshot;
          setResult(snapshot);
          if (snapshot.ready_to_fly) {
            setRunning(false);
            return snapshot;
          }
          if (isTerminalPreflightFailure(snapshot)) {
            setError(blockedMessage(snapshot, connectWarning));
            return snapshot;
          }
          await sleep(pollIntervalMs(snapshot));
        }
        if (abortRef.current) {
          return null;
        }
        setError(timeoutMessage(latest, connectWarning));
        return latest;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Preflight checks failed.";
        setError(message);
        return null;
      } finally {
        setRunning(false);
      }
    },
    [token],
  );

  return {
    running,
    result,
    error,
    runChecks,
    reset,
    passed: result?.ready_to_fly === true,
  };
}
