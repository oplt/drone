import { useCallback, useEffect, useRef, useState } from "react";
import {
  extractWarehouseStructure,
  fetchWarehouseStructure,
  type WarehouseStructureExtractParams,
  type WarehouseStructureResponse,
} from "../api/warehouseInspectionApi";
import { structureNeedsReviewMessage } from "../utils/structureQualityCopy";
import { toMessage } from "../warehousePageSupport";

export type UseWarehouseStructureResult = {
  structure: WarehouseStructureResponse | null;
  extractionStatus:
    | "not_started"
    | "queued"
    | "running"
    | "ready"
    | "needs_review"
    | "failed";
  loading: boolean;
  extracting: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Trigger extraction and resolve once a fresh result has been persisted. */
  extract: (params?: WarehouseStructureExtractParams) => Promise<void>;
};

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 120_000;
const PASSIVE_REFRESH_MS = 15_000;

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Loads the most recent detected warehouse structure (aisle/rack overlays) and
 * exposes a re-runnable extraction trigger. ``extract`` resolves only after the
 * worker has written a *newer* structure than the one currently shown, so the
 * caller can refresh scan targets immediately afterwards.
 */
export function useWarehouseStructure(
  warehouseMapId: number | null,
  token?: string | null,
): UseWarehouseStructureResult {
  const [structure, setStructure] = useState<WarehouseStructureResponse | null>(
    null,
  );
  const [extractionStatus, setExtractionStatus] =
    useState<UseWarehouseStructureResult["extractionStatus"]>("not_started");
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generatedAtRef = useRef<string | null>(null);

  const fetchOnce =
    useCallback(async (): Promise<WarehouseStructureResponse | null> => {
      if (warehouseMapId == null) return null;
      try {
        const result = await fetchWarehouseStructure(warehouseMapId, token);
        generatedAtRef.current = result.generated_at ?? null;
        setExtractionStatus(result.status);
        setStructure(
          result.status === "ready" ||
            result.status === "needs_review" ||
            result.status === "failed"
            ? result
            : null,
        );
        setError(
          result.status === "failed"
            ? result.error_message ?? "Structure extraction failed."
            : result.status === "needs_review"
              ? structureNeedsReviewMessage(
                  result.quality_reasons?.length
                    ? result.quality_reasons
                    : result.summary.quality?.reasons,
                )
            : null,
        );
        return result;
      } catch (cause) {
        setStructure(null);
        setExtractionStatus("not_started");
        setError(`Warehouse structure could not be loaded: ${toMessage(cause)}`);
        return null;
      }
    }, [token, warehouseMapId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await fetchOnce();
    } finally {
      setLoading(false);
    }
  }, [fetchOnce]);

  useEffect(() => {
    if (warehouseMapId == null) {
      setStructure(null);
      setExtractionStatus("not_started");
      generatedAtRef.current = null;
      return;
    }
    if (extractionStatus === "failed") {
      return;
    }
    let cancelled = false;
    void refresh();
    const intervalMs =
      extracting ||
      extractionStatus === "queued" ||
      extractionStatus === "running"
        ? POLL_INTERVAL_MS
        : PASSIVE_REFRESH_MS;
    const timer = window.setInterval(() => {
      if (!cancelled) void fetchOnce();
    }, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    extracting,
    extractionStatus,
    fetchOnce,
    refresh,
    warehouseMapId,
  ]);

  const extract = useCallback(
    async (params: WarehouseStructureExtractParams = {}) => {
      if (warehouseMapId == null) return;
      setExtracting(true);
      setError(null);
      setExtractionStatus("queued");
      const before = generatedAtRef.current;
      try {
        await extractWarehouseStructure(warehouseMapId, params, token);
        const deadline = Date.now() + POLL_TIMEOUT_MS;
        while (Date.now() < deadline) {
          await delay(POLL_INTERVAL_MS);
          const result = await fetchOnce();
          if (result?.status === "failed") {
            throw new Error(
              result.error_message ?? "Structure extraction worker failed.",
            );
          }
          if (
            result?.status === "needs_review" &&
            result.generated_at &&
            result.generated_at !== before
          ) {
            return;
          }
          if (
            result?.status === "ready" &&
            result.generated_at &&
            result.generated_at !== before
          ) {
            return;
          }
        }
        setError(
          "Structure extraction is taking longer than expected. It will appear once the worker finishes.",
        );
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Structure extraction could not be started.",
        );
        throw err;
      } finally {
        setExtracting(false);
      }
    },
    [fetchOnce, token, warehouseMapId],
  );

  return {
    structure,
    extractionStatus,
    loading,
    extracting,
    error,
    refresh,
    extract,
  };
}
