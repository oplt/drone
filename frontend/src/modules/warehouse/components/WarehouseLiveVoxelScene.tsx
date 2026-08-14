import { useMemo } from "react";
import Box from "@mui/material/Box";
import { Canvas } from "@react-three/fiber";
import type { CachedLiveMapChunk } from "../hooks/useLiveMapChunkCache";
import type { WarehouseMapPlacementViewerProps } from "../hooks/useWarehouseMapPlacement";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import type { WarehouseStructureSummary } from "../api/warehouseInspectionApi";
import { inferLayerKey } from "../utils/liveMapLayerUtils";
import { chunkStateKey } from "../utils/liveMapChunkRetention";
import { LiveVoxelMapContent } from "./liveVoxel/scene/LiveVoxelMapContent";
import type { LiveVoxelLayers, LiveVoxelRenderOptions } from "./liveVoxel/scene/liveVoxelSceneTypes";

export type { LiveVoxelLayers, LiveVoxelRenderOptions } from "./liveVoxel/scene/liveVoxelSceneTypes";

export function WarehouseLiveVoxelScene({
  state,
  layers,
  cachedChunks,
  renderOptions,
  mapPlacement = null,
  structure = null,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
  mapPlacement?: WarehouseMapPlacementViewerProps | null;
  structure?: WarehouseStructureSummary | null;
}) {
  const metadataById = useMemo(() => {
    const map = new Map<string, { layer: ReturnType<typeof inferLayerKey>; source?: string | null }>();
    for (const chunk of state.chunks) {
      map.set(chunkStateKey(chunk), {
        layer: inferLayerKey(chunk),
        source: chunk.source,
      });
    }
    return map;
  }, [state.chunks]);

  return (
    <Box sx={{ height: "min(78vh, 920px)", minHeight: "60vh", bgcolor: "#071113", position: "relative" }}>
      <Canvas
        data-testid="warehouse-live-voxel-map"
        camera={{
          position: [8, -12, 7],
          fov: 50,
          near: 0.05,
          far: 500,
        }}
        gl={{
          antialias: true,
          powerPreference: "high-performance",
        }}
      >
        <color attach="background" args={["#071113"]} />
        <LiveVoxelMapContent
          state={state}
          layers={layers}
          cachedChunks={cachedChunks}
          renderOptions={renderOptions}
          metadataById={metadataById}
          mapPlacement={mapPlacement}
          structure={structure}
        />
      </Canvas>
    </Box>
  );
}
