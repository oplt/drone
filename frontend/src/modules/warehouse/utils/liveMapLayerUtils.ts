import type {
  WarehouseLiveMapManifestSummary,
  WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

export type LiveMapLayerKey =
  | "rgbdColored"
  | "mid360LiDAR"
  | "nvbloxColor"
  | "nvbloxEsdf"
  | "nvbloxTsdf"
  | "nvbloxMesh"
  | "dronePath"
  | "grid";

export type LiveMapColorMode = "rgb" | "height" | "distance" | "layer";

/** Layers offered in the Warehouse 3D map UI for scan inspection / review. */
export const MAP_INSPECTION_LAYER_KEYS: LiveMapLayerKey[] = [
  "rgbdColored",
  "mid360LiDAR",
  "nvbloxColor",
  "nvbloxMesh",
];

export const LIVE_MAP_LAYER_LABELS: Record<LiveMapLayerKey, string> = {
  rgbdColored: "RGB-D Colored Cloud",
  mid360LiDAR: "Mid360 LiDAR Raw",
  nvbloxColor: "nvBlox Color Layer",
  nvbloxEsdf: "nvBlox ESDF / Costmap",
  nvbloxTsdf: "nvBlox TSDF",
  nvbloxMesh: "nvBlox Mesh",
  dronePath: "Drone Path",
  grid: "Grid",
};

export const DEFAULT_LAYER_VISIBILITY: Record<LiveMapLayerKey, boolean> = {
  rgbdColored: true,
  mid360LiDAR: false,
  nvbloxColor: false,
  nvbloxEsdf: false,
  nvbloxTsdf: false,
  nvbloxMesh: false,
  dronePath: true,
  grid: true,
};

export const DEFAULT_LAYER_POINT_BUDGET: Record<LiveMapLayerKey, number> = {
  rgbdColored: 120_000,
  mid360LiDAR: 80_000,
  nvbloxColor: 100_000,
  nvbloxEsdf: 60_000,
  nvbloxTsdf: 60_000,
  nvbloxMesh: 0,
  dronePath: 0,
  grid: 0,
};

const LAYER_COLORS: Record<LiveMapLayerKey, [number, number, number]> = {
  rgbdColored: [0.95, 0.55, 0.2],
  mid360LiDAR: [0.2, 0.85, 0.95],
  nvbloxColor: [0.45, 0.95, 0.35],
  nvbloxEsdf: [0.95, 0.35, 0.55],
  nvbloxTsdf: [0.75, 0.45, 0.95],
  nvbloxMesh: [0.8, 0.8, 0.8],
  dronePath: [1, 1, 1],
  grid: [0.5, 0.5, 0.5],
};

export function inferLayerKey(chunk: WarehouseLiveVoxelChunk): LiveMapLayerKey {
  const layer = chunk.layer ?? chunk.layer_type ?? null;
  if (layer === "rgbd_colored") return "rgbdColored";
  if (layer === "mid360_lidar") return "mid360LiDAR";
  if (layer === "nvblox_color") return "nvbloxColor";
  if (layer === "nvblox_esdf") return "nvbloxEsdf";
  if (layer === "nvblox_tsdf") return "nvbloxTsdf";
  if (layer === "nvblox_occupancy") return "nvbloxEsdf";
  if (layer === "nvblox_mesh") return "nvbloxMesh";

  if (chunk.source === "rgbd_colored") return "rgbdColored";
  if (chunk.source === "mid360_raw") return "mid360LiDAR";
  if (chunk.source === "nvblox_color") return "nvbloxColor";
  if (chunk.source === "nvblox_esdf") return "nvbloxEsdf";
  if (chunk.source === "nvblox_tsdf") return "nvbloxTsdf";
  if (chunk.source === "nvblox_occupancy") return "nvbloxEsdf";
  if (chunk.source === "nvblox_mesh") return "nvbloxMesh";

  const id = chunk.id.toLowerCase();
  if (id.startsWith("rgbd_")) return "rgbdColored";
  if (id.startsWith("mid360_")) return "mid360LiDAR";
  if (id.startsWith("nvblox_color_")) return "nvbloxColor";
  if (id.startsWith("nvblox_esdf_")) return "nvbloxEsdf";
  if (id.startsWith("nvblox_tsdf_")) return "nvbloxTsdf";
  if (id.startsWith("nvblox_occupancy_")) return "nvbloxEsdf";
  if (id.startsWith("nvblox_mesh_")) return "nvbloxMesh";
  if (chunk.kind === "esdf" || chunk.kind === "costmap" || chunk.kind === "occupancy")
    return "nvbloxEsdf";
  if (chunk.kind === "mesh") return "nvbloxMesh";
  return "mid360LiDAR";
}

export function layerColor(layer: LiveMapLayerKey): [number, number, number] {
  return LAYER_COLORS[layer];
}

export function countPointsByLayer(
  chunks: WarehouseLiveVoxelChunk[],
): Record<LiveMapLayerKey, number> {
  const counts: Record<LiveMapLayerKey, number> = {
    rgbdColored: 0,
    mid360LiDAR: 0,
    nvbloxColor: 0,
    nvbloxEsdf: 0,
    nvbloxTsdf: 0,
    nvbloxMesh: 0,
    dronePath: 0,
    grid: 0,
  };

  for (const chunk of chunks) {
    const layer = inferLayerKey(chunk);
    counts[layer] += chunk.point_count ?? 0;
  }

  return counts;
}

export function hasColoredMapLayers(chunks: WarehouseLiveVoxelChunk[]): boolean {
  return chunks.some((chunk) => {
    const layer = inferLayerKey(chunk);
    return (
      layer === "rgbdColored" ||
      layer === "nvbloxColor" ||
      layer === "nvbloxEsdf" ||
      layer === "nvbloxTsdf"
    );
  });
}

export function isRawLidarOnlyMap(
  chunks: WarehouseLiveVoxelChunk[],
  manifest?: WarehouseLiveMapManifestSummary | null,
): boolean {
  if (manifest?.raw_lidar_only) return true;
  if (manifest?.rgbd_colored_available || manifest?.nvblox_available) {
    return false;
  }
  const hasRaw = chunks.some((chunk) => inferLayerKey(chunk) === "mid360LiDAR");
  return hasRaw && !hasColoredMapLayers(chunks);
}

export type { WarehouseLiveMapManifestSummary };

export function defaultLayerVisibilityForChunks(
  chunks: WarehouseLiveVoxelChunk[],
  manifest?: WarehouseLiveMapManifestSummary | null,
): Record<LiveMapLayerKey, boolean> {
  const available = chunksAvailableByLayer(chunks, manifest);
  const next: Record<LiveMapLayerKey, boolean> = {
    rgbdColored: false,
    mid360LiDAR: false,
    nvbloxColor: false,
    nvbloxEsdf: false,
    nvbloxTsdf: false,
    nvbloxMesh: false,
    dronePath: true,
    grid: true,
  };

  if (isRawLidarOnlyMap(chunks, manifest)) {
    next.mid360LiDAR = true;
    return next;
  }

  const layerKeys: LiveMapLayerKey[] = [...MAP_INSPECTION_LAYER_KEYS];
  for (const key of layerKeys) {
    if (available[key] > 0) {
      next[key] = true;
    }
  }

  if ((available.rgbdColored > 0 || available.nvbloxColor > 0) && available.mid360LiDAR > 0) {
    next.mid360LiDAR = false;
  }

  return next;
}

const MANIFEST_SOURCE_TO_LAYER_KEY: Record<string, LiveMapLayerKey> = {
  rgbd_colored: "rgbdColored",
  mid360_raw: "mid360LiDAR",
  mid360_lidar: "mid360LiDAR",
  nvblox_color: "nvbloxColor",
  nvblox_esdf: "nvbloxEsdf",
  nvblox_tsdf: "nvbloxTsdf",
  nvblox_mesh: "nvbloxMesh",
};

export const LAYER_CAPTURE_UNAVAILABLE: Partial<Record<LiveMapLayerKey, string>> = {
  nvbloxColor:
    "Integrated nvBlox color voxels (world frame). Re-scan after the latest backend update if this layer only shows ceiling-height points.",
};

export function countChunksByLayerKey(
  chunks: WarehouseLiveVoxelChunk[],
): Record<LiveMapLayerKey, number> {
  const counts: Record<LiveMapLayerKey, number> = {
    rgbdColored: 0,
    mid360LiDAR: 0,
    nvbloxColor: 0,
    nvbloxEsdf: 0,
    nvbloxTsdf: 0,
    nvbloxMesh: 0,
    dronePath: 0,
    grid: 0,
  };

  for (const chunk of chunks) {
    const hasStoredPayload =
      Boolean(chunk.url) ||
      (chunk.point_count ?? 0) > 0 ||
      Boolean(chunk.source) ||
      Boolean(chunk.layer);
    if (!hasStoredPayload) continue;
    counts[inferLayerKey(chunk)] += 1;
  }

  return counts;
}

export function chunksAvailableByLayer(
  chunks: WarehouseLiveVoxelChunk[],
  manifest?: WarehouseLiveMapManifestSummary | null,
): Record<LiveMapLayerKey, number> {
  const counts = countChunksByLayerKey(chunks);

  const manifestCounts = manifest?.chunk_counts;
  if (manifestCounts) {
    for (const [source, rawCount] of Object.entries(manifestCounts)) {
      const layerKey = MANIFEST_SOURCE_TO_LAYER_KEY[source];
      const count = Number(rawCount);
      if (layerKey && Number.isFinite(count) && count > 0) {
        counts[layerKey] = Math.max(counts[layerKey], count);
      }
    }
  }

  return counts;
}

export function layerHasStoredChunks(
  layerKey: LiveMapLayerKey,
  chunks: WarehouseLiveVoxelChunk[],
  manifest?: WarehouseLiveMapManifestSummary | null,
): boolean {
  if (layerKey === "dronePath" || layerKey === "grid") {
    return true;
  }
  return chunksAvailableByLayer(chunks, manifest)[layerKey] > 0;
}

export const WAREHOUSE_MAP_SOURCE_TOPICS = {
  mid360_raw: "/warehouse/mid360/points",
  rgbd_colored: "/warehouse/front/rgbd/points",
  nvblox_color: "/nvblox_node/color_layer",
  nvblox_esdf: "/nvblox_node/static_esdf_pointcloud",
  nvblox_tsdf: "/nvblox_node/tsdf_layer",
  odom: "/warehouse/drone/odometry",
} as const;
