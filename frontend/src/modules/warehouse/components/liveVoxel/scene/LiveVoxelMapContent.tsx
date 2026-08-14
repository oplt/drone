import { useMemo } from "react";
import type { CachedLiveMapChunk } from "../../../hooks/useLiveMapChunkCache";
import type { WarehouseMapPlacementViewerProps } from "../../../hooks/useWarehouseMapPlacement";
import type { WarehouseLiveVoxelMapState } from "../../../hooks/useWarehouseLiveVoxelMap";
import type { WarehouseStructureSummary } from "../../../api/warehouseInspectionApi";
import { inferLayerKey, type LiveMapLayerKey } from "../../../utils/liveMapLayerUtils";
import { toRenderChunks } from "../../../utils/liveMapRenderModel";
import {
  createWarehouseSceneTransform,
  resolveDisplayedFrame,
  WAREHOUSE_MAP_FRAME,
} from "../../../utils/warehouseSceneCoordinates";
import { LiveVoxelCameraControls } from "./LiveVoxelCameraControls";
import {
  LiveVoxelBoundsChunk,
  LiveVoxelMeshChunk,
  LiveVoxelPointCloudChunk,
  LiveVoxelPreviewChunk,
} from "./LiveVoxelChunkRenderers";
import {
  LiveVoxelMapPickPlane,
  LiveVoxelScanTargetMarkers,
} from "./LiveVoxelPlacementMarkers";
import { LiveVoxelDroneMarker, LiveVoxelScanPath } from "./LiveVoxelScanPath";
import {
  distributeLiveVoxelLayerPointBudgets,
  liveVoxelLayerVisible,
} from "./liveVoxelSceneBudget";
import type { LiveVoxelLayers, LiveVoxelRenderOptions } from "./liveVoxelSceneTypes";
import { LiveVoxelGroundGrid, LiveVoxelStructureOverlay } from "./LiveVoxelStructureOverlay";

export function LiveVoxelMapContent({
  state,
  layers,
  cachedChunks,
  renderOptions,
  metadataById,
  mapPlacement,
  structure = null,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
  metadataById: Map<string, { layer: LiveMapLayerKey; source?: string | null }>;
  mapPlacement?: WarehouseMapPlacementViewerProps | null;
  structure?: WarehouseStructureSummary | null;
}) {
  const cachedByStateKey = useMemo(
    () =>
      new Map(
        cachedChunks.map((chunk) => [
          `${chunk.source ?? chunk.layer ?? "unknown"}:${chunk.id}`,
          chunk,
        ]),
      ),
    [cachedChunks],
  );

  const renderPlan = useMemo(() => {
    const all = toRenderChunks(state.chunks);
    const maxPointsByKey = distributeLiveVoxelLayerPointBudgets(
      all,
      metadataById,
      renderOptions.layerPointBudget,
      layers,
    );

    return all
      .map((renderChunk) => {
        const meta = metadataById.get(renderChunk.stateKey);
        const layer = meta?.layer ?? "mid360LiDAR";
        if (!liveVoxelLayerVisible(layer, layers)) {
          return null;
        }
        const cached = cachedByStateKey.get(renderChunk.stateKey);
        if (layer === "nvbloxMesh") {
          return { renderChunk, layer, cached, maxPoints: 1, meta };
        }
        const layerBudget = renderOptions.layerPointBudget[layer] ?? 0;
        if (layerBudget <= 0) {
          return null;
        }
        const maxPoints = maxPointsByKey.get(renderChunk.stateKey) ?? 0;
        return { renderChunk, layer, cached, maxPoints, meta };
      })
      .filter(
        (item): item is NonNullable<typeof item> =>
          item !== null && (item.layer === "nvbloxMesh" || item.maxPoints > 0),
      );
  }, [cachedByStateKey, layers, metadataById, renderOptions.layerPointBudget, state.chunks]);

  const displayFrameId = useMemo(() => {
    const frames = [
      ...state.chunks.map((chunk) => chunk.frame_id),
      state.latestUpdate?.frame_id,
      ...state.scanPath.map((pose) => pose.frame_id),
    ];
    const hasFrame = frames.some((frame) => Boolean(frame?.trim()));
    return hasFrame ? resolveDisplayedFrame(frames) : WAREHOUSE_MAP_FRAME;
  }, [state.chunks, state.latestUpdate?.frame_id, state.scanPath]);

  const sceneTransform = useMemo(
    () =>
      displayFrameId && mapPlacement?.coordinateFrame
        ? createWarehouseSceneTransform(displayFrameId, mapPlacement.coordinateFrame)
        : null,
    [displayFrameId, mapPlacement?.coordinateFrame],
  );

  const cameraFrame = useMemo(() => {
    const boxes = state.chunks
      .filter((chunk) => liveVoxelLayerVisible(inferLayerKey(chunk), layers))
      .map((chunk) => chunk.bbox_local_m)
      .filter(
        (bbox): bbox is [number, number, number, number, number, number] =>
          Array.isArray(bbox) && bbox.length === 6 && bbox.every(Number.isFinite),
      );
    if (boxes.length === 0) {
      return {
        focus: [0, 0, 1.5] as [number, number, number],
        distance: 10,
        ready: false,
      };
    }
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const bbox of boxes) {
      for (let axis = 0; axis < 3; axis += 1) {
        min[axis] = Math.min(min[axis], bbox[axis]);
        max[axis] = Math.max(max[axis], bbox[axis + 3]);
      }
    }
    const focus: [number, number, number] = [
      (min[0] + max[0]) / 2,
      (min[1] + max[1]) / 2,
      (min[2] + max[2]) / 2,
    ];
    const extent = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
    return { focus, distance: Math.max(2.5, extent * 2.5), ready: true };
  }, [layers, state.chunks]);

  return (
    <>
      <ambientLight intensity={0.7} />
      <directionalLight position={[4, -6, 8]} intensity={0.8} />

      <LiveVoxelGroundGrid visible={liveVoxelLayerVisible("grid", layers)} />

      {liveVoxelLayerVisible("dronePath", layers) && <LiveVoxelScanPath state={state} />}
      {liveVoxelLayerVisible("dronePath", layers) && <LiveVoxelDroneMarker state={state} />}

      {renderPlan.map(({ renderChunk, layer, cached, maxPoints }) => {
        if (layer === "nvbloxMesh") {
          if (!liveVoxelLayerVisible("nvbloxMesh", layers)) return null;
          if (cached?.kind === "mesh") {
            return <LiveVoxelMeshChunk key={cached.id} chunk={cached} />;
          }
          return null;
        }

        const pointLayerVisible =
          (layer === "rgbdColored" && liveVoxelLayerVisible("rgbdColored", layers)) ||
          (layer === "rgbdDepth" && liveVoxelLayerVisible("rgbdDepth", layers)) ||
          (layer === "mid360LiDAR" && liveVoxelLayerVisible("mid360LiDAR", layers)) ||
          (layer === "nvbloxColor" && liveVoxelLayerVisible("nvbloxColor", layers)) ||
          (layer === "nvbloxEsdf" && liveVoxelLayerVisible("nvbloxEsdf", layers)) ||
          (layer === "nvbloxTsdf" && liveVoxelLayerVisible("nvbloxTsdf", layers));

        if (!pointLayerVisible || maxPoints <= 0) return null;

        if (
          cached &&
          (cached.kind === "point_cloud" ||
            cached.kind === "esdf" ||
            cached.kind === "costmap" ||
            cached.kind === "occupancy")
        ) {
          return (
            <LiveVoxelPointCloudChunk
              key={cached.cacheKey ?? cached.id}
              chunk={cached}
              layer={layer}
              options={renderOptions}
              maxPoints={maxPoints}
            />
          );
        }

        if (cached && cached.kind !== "mesh" && liveVoxelLayerVisible("nvbloxEsdf", layers)) {
          return <LiveVoxelBoundsChunk key={cached.id} chunk={cached} />;
        }

        if (renderChunk.previewPoints.length > 0) {
          return (
            <LiveVoxelPreviewChunk
              key={renderChunk.id}
              renderChunk={renderChunk}
              options={renderOptions}
            />
          );
        }

        return null;
      })}

      {sceneTransform ? (
        <group matrix={sceneTransform.warehouseToScene} matrixAutoUpdate={false}>
          <LiveVoxelStructureOverlay structure={structure} />
          {mapPlacement ? <LiveVoxelScanTargetMarkers mapPlacement={mapPlacement} /> : null}
        </group>
      ) : null}

      {mapPlacement && sceneTransform ? (
        <LiveVoxelMapPickPlane
          enabled={mapPlacement.pickMode && !mapPlacement.pickBlockReason}
          placementZ={mapPlacement.placementZ}
          onPick={mapPlacement.onPick}
          transform={sceneTransform}
        />
      ) : null}

      <LiveVoxelCameraControls
        pickMode={mapPlacement?.pickMode ?? false}
        focus={cameraFrame.focus}
        distance={cameraFrame.distance}
        fitKey={state.latestUpdate?.flight_id ?? "current-map"}
        fitReady={cameraFrame.ready}
      />
    </>
  );
}
