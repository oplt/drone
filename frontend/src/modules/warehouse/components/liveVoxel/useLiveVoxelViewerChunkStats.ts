import { useMemo } from "react";
import { isChunkLayerVisible } from "../../config/liveMapConfig";
import type { CachedLiveMapChunk } from "../../hooks/useLiveMapChunkCache";
import { chunkCacheKey } from "../../hooks/useLiveMapChunkCache";
import type { WarehouseLiveVoxelMapState } from "../../hooks/useWarehouseLiveVoxelMap";
import type { LiveMapLayerKey } from "../../utils/liveMapLayerUtils";
import type { LiveVoxelLayers } from "./scene/liveVoxelSceneTypes";

export function useLiveVoxelViewerChunkStats(
  state: WarehouseLiveVoxelMapState,
  resolvedFlightId: string | null,
  layers: LiveVoxelLayers,
  cachedChunks: CachedLiveMapChunk[],
  downloadedChunkIds: ReadonlySet<string>,
  inFlightChunkIds: ReadonlySet<string>,
  layerPointBudget: Record<LiveMapLayerKey, number>,
  pointsByLayer: Record<LiveMapLayerKey, number>,
  droppedChunkCount: number,
  maxConcurrentDownloads: number,
) {
  const cachedBytes = useMemo(
    () => cachedChunks.reduce((sum, entry) => sum + entry.bytes, 0),
    [cachedChunks],
  );
  const visiblePointTotal = useMemo(
    () => cachedChunks.reduce((sum, chunk) => sum + (chunk.point_count ?? 0), 0),
    [cachedChunks],
  );
  const renderStats = useMemo(() => {
    const keys = Object.keys(layerPointBudget) as LiveMapLayerKey[];
    const pointBudget = keys
      .filter((key) => layers[key])
      .reduce((sum, key) => sum + (layerPointBudget[key] ?? 0), 0);
    const renderedPointEstimate = keys
      .filter((key) => layers[key])
      .reduce(
        (sum, key) => sum + Math.min(pointsByLayer[key] ?? 0, layerPointBudget[key] ?? 0),
        0,
      );
    return { renderedPointEstimate, pointBudget, droppedChunkCount, maxConcurrentDownloads };
  }, [droppedChunkCount, layerPointBudget, layers, maxConcurrentDownloads, pointsByLayer]);
  const visiblePendingChunkCount = useMemo(() => {
    if (!resolvedFlightId) return 0;
    let pending = 0;
    for (const chunk of state.chunks) {
      if (!chunk.url || !isChunkLayerVisible(chunk, layers)) continue;
      const key = chunkCacheKey(resolvedFlightId, chunk);
      if (!downloadedChunkIds.has(key) && !inFlightChunkIds.has(key)) {
        pending += 1;
      }
    }
    return pending;
  }, [downloadedChunkIds, inFlightChunkIds, layers, resolvedFlightId, state.chunks]);

  return {
    cachedBytes,
    visiblePointTotal,
    renderStats,
    visiblePendingChunkCount,
  };
}
