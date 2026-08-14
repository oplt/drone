import { toRenderChunks } from "../../../utils/liveMapRenderModel";
import type { LiveMapLayerKey } from "../../../utils/liveMapLayerUtils";
import type { LiveVoxelLayers } from "./liveVoxelSceneTypes";

export function liveVoxelLayerVisible(
  layer: LiveMapLayerKey,
  layers: LiveVoxelLayers,
): boolean {
  return layers[layer] ?? false;
}

/** Distribute layer point budget evenly across visible layer chunks. */
export function distributeLiveVoxelLayerPointBudgets(
  chunks: ReturnType<typeof toRenderChunks>,
  metadataByKey: Map<string, { layer: LiveMapLayerKey }>,
  budget: Record<LiveMapLayerKey, number>,
  visibleLayers?: LiveVoxelLayers,
): Map<string, number> {
  const byLayer = new Map<LiveMapLayerKey, string[]>();

  for (const renderChunk of chunks) {
    const meta = metadataByKey.get(renderChunk.stateKey);
    const layer = meta?.layer ?? "mid360LiDAR";
    if (visibleLayers && !liveVoxelLayerVisible(layer, visibleLayers)) {
      continue;
    }
    byLayer.set(layer, [...(byLayer.get(layer) ?? []), renderChunk.stateKey]);
  }

  const maxPointsByKey = new Map<string, number>();
  for (const [layer, keys] of byLayer.entries()) {
    const layerBudget = budget[layer] ?? 0;
    if (layerBudget <= 0 || keys.length === 0) continue;
    const perChunk = Math.max(512, Math.floor(layerBudget / keys.length));
    for (const key of keys) {
      maxPointsByKey.set(key, perChunk);
    }
  }

  return maxPointsByKey;
}
