import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchWarehouseScannedMapLiveSnapshot } from "../api/warehouseMissionsApi";
import { clearLiveMapChunkFetchCache } from "../api/warehouseLiveMapApi";
import { mergeReplaySnapshot } from "../utils/mergeReplaySnapshot";
import { liveMapDebugLog } from "../utils/liveMapDebug";
import type { WarehouseLiveVoxelMapState } from "./useWarehouseLiveVoxelMap";
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
  manifest: null,
  token: null,
};

export function useWarehouseScannedMapReplay(
  map: WarehouseScannedMapResponse | null,
  token?: string | null,
  options: { enabled?: boolean } = {},
) {
  const [state, setState] = useState<WarehouseLiveVoxelMapState>(EMPTY_REPLAY_STATE);
  const [loading, setLoading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const loadGenerationRef = useRef(0);
  const replayFlightIdRef = useRef<string | null>(null);

  const mapJobId = map?.job_id ?? null;
  const shouldReplay = Boolean(mapJobId != null && (options.enabled ?? true));

  const reloadFromDiskManifest = useCallback(() => {
    if (replayFlightIdRef.current) {
      clearLiveMapChunkFetchCache(replayFlightIdRef.current);
    }
    setReloadToken((current) => current + 1);
  }, []);

  useEffect(() => {
    if (!shouldReplay || mapJobId == null) {
      setState(EMPTY_REPLAY_STATE);
      setLoading(false);
      return;
    }

    const generation = ++loadGenerationRef.current;
    replayFlightIdRef.current = null;
    let cancelled = false;
    setLoading(true);
    setState({
      ...EMPTY_REPLAY_STATE,
      connectionState: "connecting",
      finalizedScanJobId: mapJobId,
      token: token ?? null,
    });

    void fetchWarehouseScannedMapLiveSnapshot(mapJobId, token, { mode: "full" })
      .then((snapshot) => {
        if (cancelled || generation !== loadGenerationRef.current) return;
        replayFlightIdRef.current = snapshot.flight_id;
        const merged = mergeReplaySnapshot(snapshot);
        const latestUpdate = merged.latestUpdate;
        const hasChunks = merged.chunks.length > 0;
        liveMapDebugLog("replay_snapshot_received", {
          scanned_map_id: mapJobId,
          flight_id: snapshot.flight_id,
          manifest_source: "disk_manifest",
          chunk_count: merged.chunks.length,
          point_count: merged.chunks.reduce(
            (sum, chunk) => sum + (chunk.point_count ?? 0),
            0,
          ),
        });
        setState({
          connectionState: hasChunks
            ? snapshot.status === "empty"
              ? "empty"
              : "finalized"
            : "empty",
          chunks: merged.chunks,
          latestUpdate,
          health: latestUpdate?.health ?? EMPTY_REPLAY_STATE.health,
          scanPath: merged.scanPath,
          error: hasChunks
            ? null
            : "No stored live-map point cloud for this scan result.",
          finalizedScanJobId: mapJobId,
          lastUpdateAt: snapshot.last_update_at ?? latestUpdate?.timestamp ?? null,
          manifest: snapshot.manifest ?? null,
          token: token ?? null,
        });
      })
      .catch((error: unknown) => {
        if (cancelled || generation !== loadGenerationRef.current) return;
        setState({
          ...EMPTY_REPLAY_STATE,
          connectionState: "failed",
          error:
            error instanceof Error
              ? error.message
              : "Could not load stored live-map replay.",
          finalizedScanJobId: mapJobId,
          token: token ?? null,
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mapJobId, reloadToken, shouldReplay, token]);

  const hasReplay = useMemo(
    () => shouldReplay && state.chunks.length > 0,
    [shouldReplay, state.chunks.length],
  );

  return {
    state,
    loading,
    hasReplay,
    shouldReplay,
    reloadFromDiskManifest,
    scannedMapId: mapJobId,
    replayFlightId:
      replayFlightIdRef.current ?? state.latestUpdate?.flight_id ?? null,
  };
}
