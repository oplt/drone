import { useCallback, useRef, useState } from "react";
import {
  fetchWarehousePreflight,
  type WarehouseGoPreflight,
} from "../api/warehousePreflightApi";

const POLL_MS = 2000;
const DEFAULT_TIMEOUT_MS = 45000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

      try {
        while (!abortRef.current && Date.now() < deadline) {
          const snapshot = await fetchWarehousePreflight(token, {
            missionLoaded: options?.missionLoaded,
            deep: true,
          });
          latest = snapshot;
          setResult(snapshot);
          if (snapshot.ready_to_fly) {
            setRunning(false);
            return snapshot;
          }
          await sleep(POLL_MS);
        }
        if (abortRef.current) {
          return null;
        }
        setError("Preflight checks did not pass within the stability window.");
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
