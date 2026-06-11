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
  nvbloxColor: true,
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
  if (chunk.layer === "rgbd_colored") return "rgbdColored";
  if (chunk.layer === "mid360_lidar") return "mid360LiDAR";
  if (chunk.layer === "nvblox_color") return "nvbloxColor";
  if (chunk.layer === "nvblox_esdf") return "nvbloxEsdf";
  if (chunk.layer === "nvblox_tsdf") return "nvbloxTsdf";
  if (chunk.layer === "nvblox_mesh") return "nvbloxMesh";

  const id = chunk.id.toLowerCase();
  if (id.startsWith("rgbd_")) return "rgbdColored";
  if (id.startsWith("mid360_")) return "mid360LiDAR";
  if (id.startsWith("nvblox_color_")) return "nvbloxColor";
  if (id.startsWith("nvblox_esdf_")) return "nvbloxEsdf";
  if (id.startsWith("nvblox_tsdf_")) return "nvbloxTsdf";
  if (id.startsWith("nvblox_mesh_")) return "nvbloxMesh";
  if (chunk.kind === "esdf" || chunk.kind === "costmap") return "nvbloxEsdf";
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
): Record<LiveMapLayerKey, boolean> {
  const next = { ...DEFAULT_LAYER_VISIBILITY };
  if (isRawLidarOnlyMap(chunks)) {
    next.rgbdColored = false;
    next.nvbloxColor = false;
    next.mid360LiDAR = true;
    return next;
  }
  if (hasColoredMapLayers(chunks)) {
    next.rgbdColored = true;
    next.nvbloxColor = true;
    next.mid360LiDAR = false;
  }
  return next;
}

export const WAREHOUSE_MAP_SOURCE_TOPICS = {
  mid360_raw: "/warehouse/mid360/points",
  rgbd_colored: "/warehouse/front/rgbd/points",
  nvblox_color: "/nvblox_node/color_layer",
  nvblox_esdf: "/nvblox_node/static_esdf_pointcloud",
  nvblox_tsdf: "/nvblox_node/tsdf_layer",
  odom: "/warehouse/drone/odometry",
} as const;
