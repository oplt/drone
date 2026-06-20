import type { LiveMapLayerKey } from "../utils/liveMapLayerUtils";
import type { LiveVoxelLayers } from "../components/WarehouseLiveVoxelScene";
import type { WarehouseLiveVoxelChunk } from "../api/warehouseLiveMapApi";
import { inferLayerKey } from "../utils/liveMapLayerUtils";

export type LiveMapPreferredLayer =
  | "rgbd_colored"
  | "rgbd_xyz_uncolored"
  | "nvblox_esdf"
  | "nvblox_mesh"
  | "mid360_raw";

export type LiveMapRuntimeConfig = {
  raw_lidar: {
    enabled: boolean;
    max_hz: number;
    voxel_size: number;
    max_points: number;
  };
  frontend: {
    max_concurrent_chunk_downloads: number;
    max_points_per_layer: number;
  };
  preferred_layer: LiveMapPreferredLayer;
};

export const DEFAULT_LIVE_MAP_CONFIG: LiveMapRuntimeConfig = {
  raw_lidar: {
    enabled: false,
    max_hz: 0.5,
    voxel_size: 0.15,
    max_points: 8000,
  },
  frontend: {
    max_concurrent_chunk_downloads: 8,
    max_points_per_layer: 800_000,
  },
  preferred_layer: "rgbd_colored",
};

const LAYER_KEY_TO_SOURCE: Record<LiveMapLayerKey, string | null> = {
  rgbdColored: "rgbd_colored",
  rgbdDepth: "rgbd_xyz_uncolored",
  mid360LiDAR: "mid360_raw",
  nvbloxColor: "nvblox_color",
  nvbloxEsdf: "nvblox_esdf",
  nvbloxTsdf: "nvblox_tsdf",
  nvbloxMesh: "nvblox_mesh",
  dronePath: null,
  grid: null,
};

export function layerKeyToSource(layer: LiveMapLayerKey): string | null {
  return LAYER_KEY_TO_SOURCE[layer];
}

export function isChunkLayerVisible(
  chunk: WarehouseLiveVoxelChunk,
  visibleLayers: LiveVoxelLayers,
): boolean {
  const layerKey = inferLayerKey(chunk);
  if (layerKey === "dronePath" || layerKey === "grid") {
    return false;
  }
  return Boolean(visibleLayers[layerKey]);
}

export function filterChunksForDownload(
  chunks: WarehouseLiveVoxelChunk[],
  visibleLayers: LiveVoxelLayers,
  _preferredLayer?: LiveMapPreferredLayer,
): WarehouseLiveVoxelChunk[] {
  void _preferredLayer;
  return chunks.filter(
    (chunk) => Boolean(chunk.url) && isChunkLayerVisible(chunk, visibleLayers),
  );
}

export function mergeLiveMapConfig(
  partial?: Partial<{ live_map: Partial<LiveMapRuntimeConfig> }> | null,
): LiveMapRuntimeConfig {
  const incoming = partial?.live_map;
  if (!incoming) return DEFAULT_LIVE_MAP_CONFIG;

  return {
    raw_lidar: {
      ...DEFAULT_LIVE_MAP_CONFIG.raw_lidar,
      ...incoming.raw_lidar,
    },
    frontend: {
      ...DEFAULT_LIVE_MAP_CONFIG.frontend,
      ...incoming.frontend,
    },
    preferred_layer:
      incoming.preferred_layer ?? DEFAULT_LIVE_MAP_CONFIG.preferred_layer,
  };
}
