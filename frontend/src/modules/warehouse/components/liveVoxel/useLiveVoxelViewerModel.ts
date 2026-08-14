import { useEffect, useMemo, useRef, useState } from "react";
import type { WarehouseLiveVoxelMapState } from "../../hooks/useWarehouseLiveVoxelMap";
import { fetchWarehouseLiveMapConfig } from "../../api/warehouseLiveMapApi";
import {
  DEFAULT_LIVE_MAP_CONFIG,
  mergeLiveMapConfig,
} from "../../config/liveMapConfig";
import type { WarehouseMapPlacementViewerProps } from "../../hooks/useWarehouseMapPlacement";
import {
  chunksAvailableByLayer,
  countPointsByLayer,
  DEFAULT_LAYER_POINT_BUDGET,
  DEFAULT_LAYER_VISIBILITY,
  defaultLayerVisibilityForChunks,
  isRawLidarOnlyMap,
  type LiveMapColorMode,
  type LiveMapLayerKey,
} from "../../utils/liveMapLayerUtils";
import {
  createWarehouseSceneTransform,
  resolveDisplayedFrame,
  WAREHOUSE_MAP_FRAME,
} from "../../utils/warehouseSceneCoordinates";
import type { LiveVoxelLayers, LiveVoxelRenderOptions } from "./scene/liveVoxelSceneTypes";

export function useLiveVoxelViewerModel(
  state: WarehouseLiveVoxelMapState,
  flightId: string | null | undefined,
  scannedMapId: number | null | undefined,
  cacheMode: "live" | "replay" | undefined,
  mapPlacement: WarehouseMapPlacementViewerProps | null | undefined,
) {
  const [layers, setLayers] = useState<LiveVoxelLayers>(DEFAULT_LAYER_VISIBILITY);
  const [pointSize, setPointSize] = useState(0.035);
  const [colorMode, setColorMode] = useState<LiveMapColorMode>("rgb");
  const [layerPointBudget, setLayerPointBudget] = useState(DEFAULT_LAYER_POINT_BUDGET);
  const [highDensity, setHighDensity] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [liveMapConfig, setLiveMapConfig] = useState(DEFAULT_LIVE_MAP_CONFIG);
  const [configError, setConfigError] = useState<string | null>(null);
  const layerDefaultsFlightRef = useRef<string | null>(null);

  useEffect(() => {
    if (!state.token) return;
    void fetchWarehouseLiveMapConfig(state.token)
      .then((payload) => {
        setLiveMapConfig(mergeLiveMapConfig(payload));
        setConfigError(null);
      })
      .catch((error: unknown) => {
        setConfigError(
          error instanceof Error
            ? error.message
            : "Live-map configuration is unavailable.",
        );
      });
  }, [state.token]);

  useEffect(() => {
    if (!highDensity) {
      setLayerPointBudget(DEFAULT_LAYER_POINT_BUDGET);
      return;
    }
    const max = liveMapConfig.frontend.max_points_per_layer;
    setLayerPointBudget({
      ...DEFAULT_LAYER_POINT_BUDGET,
      rgbdColored: max,
      rgbdDepth: max,
      nvbloxColor: max,
      nvbloxEsdf: Math.floor(max * 0.5),
      nvbloxTsdf: Math.floor(max * 0.5),
      mid360LiDAR: Math.floor(max * 0.35),
      nvbloxMesh: 1,
    });
  }, [highDensity, liveMapConfig.frontend.max_points_per_layer]);

  const resolvedFlightId = flightId ?? state.latestUpdate?.flight_id ?? null;

  useEffect(() => {
    const flightKey =
      resolvedFlightId ?? (scannedMapId != null ? `scan:${scannedMapId}` : null);
    if (!flightKey) {
      layerDefaultsFlightRef.current = null;
      return;
    }
    if (state.chunks.length === 0) return;
    if (layerDefaultsFlightRef.current === flightKey) return;
    layerDefaultsFlightRef.current = flightKey;
    setLayers(defaultLayerVisibilityForChunks(state.chunks, state.manifest));
  }, [resolvedFlightId, scannedMapId, state.chunks.length, state.connectionState, state.manifest]);

  const rawLidarOnly = useMemo(
    () => isRawLidarOnlyMap(state.chunks, state.manifest),
    [state.chunks, state.manifest],
  );

  const resolvedCacheMode =
    cacheMode ?? (state.connectionState === "finalized" ? "replay" : "live");

  const pointsByLayer = useMemo(() => countPointsByLayer(state.chunks), [state.chunks]);
  const chunksByLayer = useMemo(
    () => chunksAvailableByLayer(state.chunks, state.manifest),
    [state.chunks, state.manifest],
  );

  const manifestChunkTotal = useMemo(() => {
    const counts = state.manifest?.chunk_counts;
    if (!counts) return state.chunks.length;
    return Object.values(counts).reduce((sum, value) => sum + Number(value), 0);
  }, [state.chunks.length, state.manifest?.chunk_counts]);

  const manifestPointTotal = useMemo(() => {
    const counts = state.manifest?.point_counts;
    if (!counts) {
      return state.chunks.reduce((sum, chunk) => sum + (chunk.point_count ?? 0), 0);
    }
    return Object.values(counts).reduce((sum, value) => sum + Number(value), 0);
  }, [state.chunks, state.manifest?.point_counts]);

  const renderOptions: LiveVoxelRenderOptions = useMemo(
    () => ({ pointSize, colorMode, layerPointBudget }),
    [colorMode, layerPointBudget, pointSize],
  );

  const scenePickBlockReason = useMemo(() => {
    if (!mapPlacement) return null;
    if (mapPlacement.pickBlockReason) return mapPlacement.pickBlockReason;
    const frameIds = [
      ...state.chunks.map((chunk) => chunk.frame_id),
      state.latestUpdate?.frame_id,
      ...state.scanPath.map((pose) => pose.frame_id),
    ];
    const populated = frameIds.filter((frame) => Boolean(frame?.trim()));
    const displayFrame = populated.length ? resolveDisplayedFrame(frameIds) : WAREHOUSE_MAP_FRAME;
    if (!displayFrame) return "Visible map layers use incompatible coordinate frames.";
    if (
      !mapPlacement.coordinateFrame ||
      !createWarehouseSceneTransform(displayFrame, mapPlacement.coordinateFrame)
    ) {
      return `No transform from displayed ${displayFrame} frame to warehouse_map.`;
    }
    return null;
  }, [mapPlacement, state.chunks, state.latestUpdate?.frame_id, state.scanPath]);

  const effectiveMapPlacement = useMemo(
    () =>
      mapPlacement ? { ...mapPlacement, pickBlockReason: scenePickBlockReason } : null,
    [mapPlacement, scenePickBlockReason],
  );

  const updateLayer = (key: LiveMapLayerKey) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  };

  const updateBudget = (key: LiveMapLayerKey, value: number) => {
    setLayerPointBudget((current) => ({ ...current, [key]: value }));
  };

  return {
    layers,
    pointSize,
    setPointSize,
    colorMode,
    setColorMode,
    layerPointBudget,
    highDensity,
    setHighDensity,
    diagnosticsOpen,
    setDiagnosticsOpen,
    liveMapConfig,
    configError,
    rawLidarOnly,
    resolvedFlightId,
    resolvedCacheMode,
    pointsByLayer,
    chunksByLayer,
    manifestChunkTotal,
    manifestPointTotal,
    renderOptions,
    scenePickBlockReason,
    effectiveMapPlacement,
    updateLayer,
    updateBudget,
  };
}
