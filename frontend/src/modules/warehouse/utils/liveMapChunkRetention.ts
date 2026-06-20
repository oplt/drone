import type { WarehouseLiveVoxelChunk } from "../api/warehouseLiveMapApi";

/** Per-layer chunk caps — sequence is scoped per source, not global. */
export const MAX_CHUNKS_PER_LAYER: Record<string, number> = {
  mid360_lidar: 32,
  mid360_raw: 32,
  rgbd_colored: 1200,
  nvblox_color: 1200,
  nvblox_esdf: 1200,
  nvblox_tsdf: 1200,
  nvblox_mesh: 80,
  unknown: 300,
};

export const LIVE_MAX_CACHED_CHUNKS_PER_LAYER = 600;
export const LIVE_MAX_CACHED_CHUNKS_RAW_LIDAR = 8;

export function chunkSourceKey(chunk: WarehouseLiveVoxelChunk): string {
  if (chunk.source) return chunk.source;
  if (chunk.layer) return chunk.layer;
  return getChunkRetentionLayer(chunk);
}

/** Stable chunk identity within a flight (source + chunk id). */
export function chunkStateKey(chunk: WarehouseLiveVoxelChunk): string {
  return `${chunkSourceKey(chunk)}:${chunk.id}`;
}

/** Cache/network key scoped to flight + source + chunk id. */
export function chunkCacheKey(
  flightId: string,
  chunk: WarehouseLiveVoxelChunk,
): string {
  return `${flightId}:${chunkStateKey(chunk)}`;
}

export function getChunkRetentionLayer(chunk: WarehouseLiveVoxelChunk): string {
  if (chunk.layer) return chunk.layer;
  if (chunk.layer_type) return chunk.layer_type;
  if (chunk.source) return chunk.source;

  const id = chunk.id.toLowerCase();
  if (id.startsWith("rgbd_")) return "rgbd_colored";
  if (id.startsWith("mid360_")) return "mid360_lidar";
  if (id.startsWith("nvblox_color_")) return "nvblox_color";
  if (id.startsWith("nvblox_esdf_")) return "nvblox_esdf";
  if (id.startsWith("nvblox_tsdf_")) return "nvblox_tsdf";
  if (id.startsWith("nvblox_mesh_")) return "nvblox_mesh";

  return "unknown";
}

export function sortLayerChunks(
  chunks: WarehouseLiveVoxelChunk[],
): WarehouseLiveVoxelChunk[] {
  return [...chunks].sort((left, right) => {
    const seqLeft = left.sequence ?? 0;
    const seqRight = right.sequence ?? 0;
    if (seqLeft !== seqRight) return seqLeft - seqRight;
    return String(left.id).localeCompare(String(right.id));
  });
}

export function limitChunksPerLayer(
  chunks: WarehouseLiveVoxelChunk[],
  limits: Record<string, number> = MAX_CHUNKS_PER_LAYER,
): WarehouseLiveVoxelChunk[] {
  const grouped = new Map<string, WarehouseLiveVoxelChunk[]>();

  for (const chunk of chunks) {
    const layer = getChunkRetentionLayer(chunk);
    const current = grouped.get(layer) ?? [];
    current.push(chunk);
    grouped.set(layer, current);
  }

  const result: WarehouseLiveVoxelChunk[] = [];
  for (const [layer, layerChunks] of grouped) {
    const limit = limits[layer] ?? limits.unknown ?? 80;
    result.push(...sortLayerChunks(layerChunks).slice(-limit));
  }

  return result;
}

export function selectDownloadableChunksPerLayer(
  chunks: WarehouseLiveVoxelChunk[],
  mode: "live" | "replay",
  options: {
    maxBytesPerChunk?: number;
    maxCachedChunksPerLayer?: number;
    maxReplayBytes?: number;
    maxReplayChunks?: number;
  } = {},
): WarehouseLiveVoxelChunk[] {
  const maxBytesPerChunk = options.maxBytesPerChunk ?? 48 * 1024 * 1024;
  const maxCachedChunksPerLayer =
    options.maxCachedChunksPerLayer ?? LIVE_MAX_CACHED_CHUNKS_PER_LAYER;
  const maxReplayBytes = options.maxReplayBytes ?? 256 * 1024 * 1024;
  const maxReplayChunks = options.maxReplayChunks ?? 512;

  const valid = chunks.filter(
    (chunk) => Boolean(chunk.url) && (chunk.byte_size ?? 0) > 0,
  );

  const grouped = new Map<string, WarehouseLiveVoxelChunk[]>();
  for (const chunk of valid) {
    const layer = getChunkRetentionLayer(chunk);
    grouped.set(layer, [...(grouped.get(layer) ?? []), chunk]);
  }

  const selected: WarehouseLiveVoxelChunk[] = [];
  for (const [layer, layerChunks] of grouped.entries()) {
    const sorted = sortLayerChunks(layerChunks).filter(
      (chunk) => (chunk.byte_size ?? 0) <= maxBytesPerChunk,
    );

    if (mode === "live") {
      const limit =
        layer === "mid360_lidar" || layer === "mid360_raw"
          ? Math.min(maxCachedChunksPerLayer, LIVE_MAX_CACHED_CHUNKS_RAW_LIDAR)
          : maxCachedChunksPerLayer;
      selected.push(...sorted.slice(-limit));
      continue;
    }

    selected.push(...sorted);
  }

  if (mode === "live") {
    return selected;
  }

  // Replay: download every manifest chunk; byte caps are advisory only for progress UI.
  void maxReplayBytes;
  void maxReplayChunks;
  return sortLayerChunks(selected);
}
