import type { WarehouseLiveMapMessage } from "../api/warehouseLiveMapApi";
import { applyWarehouseLiveVoxelMessageBatch } from "./warehouseLiveVoxelMapTypes";
import { WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH, WAREHOUSE_LIVE_VOXEL_STALE_AFTER_MS } from "./warehouseLiveVoxelMapConstants";
import type { WarehouseLiveVoxelMergedState } from "./warehouseLiveVoxelMapTypes";
import type { WarehouseLiveVoxelTransportSetters } from "./warehouseLiveVoxelMapTransportSession";

export function createWarehouseLiveVoxelMessageLoop(
  streamPausedRef: { current: boolean },
  stateRef: { current: WarehouseLiveVoxelMergedState },
  setters: WarehouseLiveVoxelTransportSetters,
) {
  let raf: number | null = null;
  let staleTimer: number | null = null;
  const queuedMessages: WarehouseLiveMapMessage[] = [];

  const scheduleStaleCheck = () => {
    if (staleTimer != null) window.clearTimeout(staleTimer);
    staleTimer = window.setTimeout(() => {
      setters.setConnectionState((current) => (current === "live" ? "stale" : current));
    }, WAREHOUSE_LIVE_VOXEL_STALE_AFTER_MS);
  };

  const flush = () => {
    raf = null;
    if (queuedMessages.length === 0) return;

    const batch = queuedMessages.splice(0, queuedMessages.length);
    const result = applyWarehouseLiveVoxelMessageBatch(stateRef.current, batch);
    stateRef.current = result.merged;
    setters.setChunksById(result.merged.chunksById);
    setters.setProvisionalCandidatesByKey(result.merged.provisionalCandidatesByKey);
    setters.setCoverageRepairHints(result.merged.coverageRepairHints);
    setters.setCoordinateState(result.merged.coordinateState);
    setters.setScanPath(result.merged.scanPath);

    if (result.newestUpdate) {
      setters.setLatestUpdate(result.newestUpdate);
      setters.setHealth(result.newestUpdate.health ?? WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH);
    }
    if (result.newestLastUpdateAt) setters.setLastUpdateAt(result.newestLastUpdateAt);
    if (result.finalizedId != null) setters.setFinalizedScanJobId(result.finalizedId);
    if (result.newestSnapshotStatus) setters.setConnectionState(result.newestSnapshotStatus);
    if (result.newestManifest) setters.setManifest(result.newestManifest);
    scheduleStaleCheck();
  };

  const applyMessage = (message: WarehouseLiveMapMessage) => {
    if (streamPausedRef.current && message.type !== "live_map_finalized") return;
    queuedMessages.push(message);
    if (raf != null) return;
    raf = window.requestAnimationFrame(flush);
  };

  const dispose = () => {
    if (staleTimer != null) window.clearTimeout(staleTimer);
    if (raf != null) window.cancelAnimationFrame(raf);
    staleTimer = null;
    raf = null;
    queuedMessages.length = 0;
  };

  return { applyMessage, dispose, scheduleStaleCheck };
}
