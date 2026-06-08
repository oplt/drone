import { useEffect, useMemo, useState } from "react";
import { fetchWarehouseScannedMapLiveSnapshot } from "../api/warehouseMissionsApi";
import {
  applyWarehouseLiveMapMessage,
  type WarehouseLiveVoxelMapState,
} from "./useWarehouseLiveVoxelMap";
import type { WarehouseScannedMapResponse } from "../types/missions";

const EMPTY_REPLAY_STATE: WarehouseLiveVoxelMapState = {
  connectionState: "empty",
  chunks: [],
  latestUpdate: null,
  health: {
    coverage_percent: null,
    drift_estimate_m: null,
    stale_costmap: false,
    missing_mesh: true,
    missing_point_cloud: true,
    nvblox_ready: false,
    mapping_recording: false,
    stack_running: false,
  },
  scanPath: [],
  error: null,
  finalizedScanJobId: null,
  lastUpdateAt: null,
  token: null,
};

export function useWarehouseScannedMapReplay(
  map: WarehouseScannedMapResponse | null,
  token?: string | null,
  options: { enabled?: boolean } = {},
) {
  const [state, setState] = useState<WarehouseLiveVoxelMapState>(EMPTY_REPLAY_STATE);
  const [loading, setLoading] = useState(false);

  const shouldReplay = Boolean(map && (options.enabled ?? true));

  useEffect(() => {
    if (!shouldReplay || !map) {
      setState(EMPTY_REPLAY_STATE);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setState({
      ...EMPTY_REPLAY_STATE,
      connectionState: "connecting",
      finalizedScanJobId: map.job_id,
      token: token ?? null,
    });

    void fetchWarehouseScannedMapLiveSnapshot(map.job_id, token)
      .then((snapshot) => {
        if (cancelled) return;
        const merged = applyWarehouseLiveMapMessage(
          {
            chunksById: new Map(),
            scanPath: [],
          },
          snapshot,
        );
        const latestUpdate = snapshot.updates.at(-1) ?? null;
        const hasChunks = merged.chunksById.size > 0;
        setState({
          connectionState: hasChunks
            ? snapshot.status === "empty"
              ? "empty"
              : "finalized"
            : "empty",
          chunks: Array.from(merged.chunksById.values()),
          latestUpdate,
          health: latestUpdate?.health ?? EMPTY_REPLAY_STATE.health,
          scanPath: merged.scanPath,
          error: hasChunks
            ? null
            : "No stored live-map point cloud for this scan result.",
          finalizedScanJobId: map.job_id,
          lastUpdateAt: snapshot.last_update_at ?? latestUpdate?.timestamp ?? null,
          token: token ?? null,
        });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          ...EMPTY_REPLAY_STATE,
          connectionState: "failed",
          error:
            error instanceof Error
              ? error.message
              : "Could not load stored live-map replay.",
          finalizedScanJobId: map.job_id,
          token: token ?? null,
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [map, shouldReplay, token]);

  const hasReplay = useMemo(
    () => shouldReplay && state.chunks.length > 0,
    [shouldReplay, state.chunks.length],
  );

  return { state, loading, hasReplay, shouldReplay };
}
