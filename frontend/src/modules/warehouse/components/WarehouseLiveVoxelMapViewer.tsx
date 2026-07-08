import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  Tab,
  Tabs,
  Typography,
  CircularProgress,
} from "@mui/material";
import { WarehouseCoordinateSetupPanel } from "./WarehouseCoordinateSetupPanel";
import { WarehouseLayerBudgetSlider } from "./WarehouseLayerBudgetSlider";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import { useLiveMapChunkCache, chunkCacheKey } from "../hooks/useLiveMapChunkCache";
import {
  fetchWarehouseLiveMapConfig,
} from "../api/warehouseLiveMapApi";
import {
  DEFAULT_LIVE_MAP_CONFIG,
  isChunkLayerVisible,
  mergeLiveMapConfig,
} from "../config/liveMapConfig";
import {
  WarehouseLiveVoxelScene,
  type LiveVoxelLayers,
  type LiveVoxelRenderOptions,
} from "./WarehouseLiveVoxelScene";
import type { WarehouseMapPlacementViewerProps, WarehouseMapPlacementPanelProps } from "../hooks/useWarehouseMapPlacement";
import { useWarehouseStructure } from "../hooks/useWarehouseStructure";
import {
  WarehouseLiveVoxelHeader,
  WarehouseLiveVoxelHealthChips,
  WarehouseLiveVoxelMetrics,
  WarehouseLiveVoxelOverlay,
} from "./WarehouseLiveVoxelStatus";
import {
  WarehouseMappingHealthPanel,
  type WarehouseMappingRuntimeStatus,
} from "./WarehouseMappingHealthPanel";
import type { WarehouseMappingStackStatus } from "../api/warehouseMissionsApi";
import {
  chunksAvailableByLayer,
  countPointsByLayer,
  DEFAULT_LAYER_POINT_BUDGET,
  DEFAULT_LAYER_VISIBILITY,
  defaultLayerVisibilityForChunks,
  isRawLidarOnlyMap,
  layerHasStoredChunks,
  LAYER_CAPTURE_UNAVAILABLE,
  LIVE_MAP_LAYER_LABELS,
  MAP_INSPECTION_LAYER_KEYS,
  type LiveMapColorMode,
  type LiveMapLayerKey,
} from "../utils/liveMapLayerUtils";
import {
  createWarehouseSceneTransform,
  resolveDisplayedFrame,
  WAREHOUSE_MAP_FRAME,
} from "../utils/warehouseSceneCoordinates";

export function WarehouseLiveVoxelMapViewer({
  state,
  flightId = null,
  hidden = false,
  mappingStatus = null,
  mappingStackStatus = null,
  cacheMode,
  mapMode = "live",
  scannedMapId = null,
  onReloadReplay,
  onClearMap,
  onToggleStream,
  streamPaused = false,
  mapPlacement = null,
  warehouseMapId = null,
  mapPlacementPanel = null,
  mapDetailTab = "layers",
  onMapDetailTabChange,
  onCoordinateSetupError,
  coordinateSetupToken = null,
  replayLoading = false,
}: {
  state: WarehouseLiveVoxelMapState;
  flightId?: string | null;
  hidden?: boolean;
  mappingStatus?: WarehouseMappingRuntimeStatus | null;
  mappingStackStatus?: WarehouseMappingStackStatus | null;
  cacheMode?: "live" | "replay";
  mapMode?: "live" | "replay";
  scannedMapId?: number | null;
  onReloadReplay?: () => void;
  onClearMap?: () => void;
  onToggleStream?: () => void;
  streamPaused?: boolean;
  mapPlacement?: WarehouseMapPlacementViewerProps | null;
  warehouseMapId?: number | null;
  mapPlacementPanel?: WarehouseMapPlacementPanelProps | null;
  mapDetailTab?: "layers" | "coordinateSetup";
  onMapDetailTabChange?: (tab: "layers" | "coordinateSetup") => void;
  onCoordinateSetupError?: (message: string) => void;
  coordinateSetupToken?: string | null;
  replayLoading?: boolean;
}) {
  const [layers, setLayers] = useState<LiveVoxelLayers>(DEFAULT_LAYER_VISIBILITY);
  const [pointSize, setPointSize] = useState(0.035);
  const [colorMode, setColorMode] = useState<LiveMapColorMode>("rgb");
  const [layerPointBudget, setLayerPointBudget] = useState(
    DEFAULT_LAYER_POINT_BUDGET,
  );
  const [liveMapConfig, setLiveMapConfig] = useState(DEFAULT_LIVE_MAP_CONFIG);
  const [configError, setConfigError] = useState<string | null>(null);
  const layerDefaultsFlightRef = useRef<string | null>(null);

  const structure = useWarehouseStructure(
    mapDetailTab === "coordinateSetup" ? warehouseMapId : null,
    coordinateSetupToken,
  );

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
    setLayerPointBudget((current) => ({
      ...current,
      rgbdColored: liveMapConfig.frontend.max_points_per_layer,
      nvbloxColor: liveMapConfig.frontend.max_points_per_layer,
      nvbloxEsdf: Math.floor(liveMapConfig.frontend.max_points_per_layer * 0.5),
      nvbloxTsdf: Math.floor(liveMapConfig.frontend.max_points_per_layer * 0.5),
      mid360LiDAR: Math.floor(liveMapConfig.frontend.max_points_per_layer * 0.35),
      nvbloxMesh: 1,
    }));
  }, [liveMapConfig.frontend.max_points_per_layer]);

  const resolvedFlightId =
    flightId ?? state.latestUpdate?.flight_id ?? null;

  useEffect(() => {
    const flightKey =
      resolvedFlightId ??
      (scannedMapId != null ? `scan:${scannedMapId}` : null);
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
  const { cachedChunks, downloadedChunkIds, inFlightChunkIds } =
    useLiveMapChunkCache(resolvedFlightId, state.chunks, state.token, {
      mode: resolvedCacheMode,
      visibleLayers: layers,
      config: liveMapConfig,
    });
  const cachedBytes = useMemo(
    () => cachedChunks.reduce((sum, entry) => sum + entry.bytes, 0),
    [cachedChunks],
  );
  const pointsByLayer = useMemo(
    () => countPointsByLayer(state.chunks),
    [state.chunks],
  );
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
      return state.chunks.reduce(
        (sum, chunk) => sum + (chunk.point_count ?? 0),
        0,
      );
    }
    return Object.values(counts).reduce((sum, value) => sum + Number(value), 0);
  }, [state.chunks, state.manifest?.point_counts]);
  const visiblePointTotal = useMemo(
    () =>
      cachedChunks.reduce((sum, chunk) => sum + (chunk.point_count ?? 0), 0),
    [cachedChunks],
  );
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
  }, [
    downloadedChunkIds,
    inFlightChunkIds,
    layers,
    resolvedFlightId,
    state.chunks,
  ]);

  const renderOptions: LiveVoxelRenderOptions = useMemo(
    () => ({
      pointSize,
      colorMode,
      layerPointBudget,
    }),
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
    const displayFrame = populated.length
      ? resolveDisplayedFrame(frameIds)
      : WAREHOUSE_MAP_FRAME;
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
      mapPlacement
        ? { ...mapPlacement, pickBlockReason: scenePickBlockReason }
        : null,
    [mapPlacement, scenePickBlockReason],
  );

  const updateLayer = (key: LiveMapLayerKey) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  };

  const updateBudget = (key: LiveMapLayerKey, value: number) => {
    setLayerPointBudget((current) => ({ ...current, [key]: value }));
  };

  return (
    <Stack spacing={1.25}>
      {configError ? (
        <Alert severity="warning">
          Live-map configuration could not be loaded. Safe display defaults are active. {configError}
        </Alert>
      ) : null}
      {rawLidarOnly && (
        <Alert severity="warning">
          This saved map contains raw Mid360 LiDAR only. RGB-D or nvBlox colored
          layers were not available when the scan was finalized.
        </Alert>
      )}
      <WarehouseLiveVoxelHeader
        state={state}
        cachedBytes={cachedBytes}
        streamPaused={streamPaused}
      />
      <WarehouseMappingHealthPanel
        status={mappingStatus}
        liveHealth={state.health}
        mappingStackStatus={mappingStackStatus}
      />

      <WarehouseLiveVoxelMetrics
        state={state}
        mappingStackStatus={mappingStackStatus}
        pointsByLayer={pointsByLayer}
        cachedBytes={cachedBytes}
      />
      <Typography variant="caption" color="text.secondary">
        Mode: {mapMode} · flight: {flightId ?? state.latestUpdate?.flight_id ?? "—"}
        {scannedMapId != null ? ` · scan #${scannedMapId}` : ""} · manifest:{" "}
        {state.manifest ? "disk" : "live"} · chunks{" "}
        {cachedChunks.length}/{manifestChunkTotal || state.chunks.length} loaded ·
        points {visiblePointTotal.toLocaleString()}/
        {manifestPointTotal.toLocaleString()} visible
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Downloads: {downloadedChunkIds.size} complete, {inFlightChunkIds.size} in
        flight
        {visiblePendingChunkCount > 0
          ? ` · ${visiblePendingChunkCount} visible chunk(s) queued`
          : ""}
      </Typography>



      <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
        {onReloadReplay && (
          <Button size="small" variant="outlined" onClick={onReloadReplay}>
            Refresh map from disk
          </Button>
        )}
        {onToggleStream && (
          <Button size="small" variant="outlined" onClick={onToggleStream}>
            {streamPaused ? "Resume stream" : "Pause stream"}
          </Button>
        )}
        {onClearMap && (
          <Button size="small" variant="outlined" onClick={onClearMap}>
            Clear accumulated map
          </Button>
        )}
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="live-map-color-mode">Color mode</InputLabel>
          <Select
            labelId="live-map-color-mode"
            label="Color mode"
            value={colorMode}
            onChange={(event) =>
              setColorMode(event.target.value as LiveMapColorMode)
            }
          >
            <MenuItem value="rgb">RGB</MenuItem>
            <MenuItem value="height">Height</MenuItem>
            <MenuItem value="distance">Distance</MenuItem>
            <MenuItem value="layer">Layer color</MenuItem>
          </Select>
        </FormControl>
        <Box sx={{ width: 180, px: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Point size
          </Typography>
          <Slider
            size="small"
            min={0.01}
            max={0.12}
            step={0.005}
            value={pointSize}
            onChange={(_event, value) => setPointSize(Number(value))}
          />
        </Box>
      </Stack>

      <Box
        sx={{
          borderRadius: 1,
          overflow: "hidden",
          border: "1px solid",
          borderColor: "divider",
          position: "relative",
          cursor:
            mapPlacement?.pickMode && !scenePickBlockReason
              ? "crosshair"
              : "default",
        }}
      >
          {!hidden && (
              <WarehouseLiveVoxelScene
                  state={state}
                  layers={layers}
                  cachedChunks={cachedChunks}
                  renderOptions={renderOptions}
                  mapPlacement={effectiveMapPlacement}
                  structure={
                    structure.structure?.status === "ready"
                      ? structure.structure.summary
                      : null
                  }
              />
          )}
        {mapPlacement?.pickMode ? (
          <Box
            sx={{
              position: "absolute",
              top: 8,
              left: 8,
              right: 8,
              zIndex: 2,
              pointerEvents: "none",
            }}
          >
            <Alert severity={scenePickBlockReason ? "warning" : "info"} sx={{ py: 0.25 }}>
              {scenePickBlockReason ??
                `Click the map to place a bin target at warehouse Z=${mapPlacement.placementZ.toFixed(2)} m. Orange = saved targets, yellow = draft.`}
            </Alert>
          </Box>
        ) : null}
        {replayLoading ? (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              bgcolor: "rgba(0,0,0,0.45)",
              zIndex: 3,
              pointerEvents: "none",
            }}
          >
            <Stack spacing={0.5} alignItems="center">
              <CircularProgress size={28} sx={{ color: "common.white" }} />
              <Typography variant="caption" sx={{ color: "common.white" }}>
                Loading scan replay from disk…
              </Typography>
            </Stack>
          </Box>
        ) : null}
        {["empty", "connecting", "reconnecting", "stale", "failed"].includes(
          state.connectionState,
        ) && !replayLoading && <WarehouseLiveVoxelOverlay state={state} />}
      </Box>

      <WarehouseLiveVoxelHealthChips state={state} />

      {warehouseMapId != null ? (
        <Tabs
          value={mapDetailTab}
          onChange={(_, value: "layers" | "coordinateSetup") =>
            onMapDetailTabChange?.(value)
          }
          variant="fullWidth"
        >
          <Tab value="layers" label="Layers" />
          <Tab value="coordinateSetup" label="Coordinate Setup" />
        </Tabs>
      ) : (
        <Typography variant="subtitle2" color="text.secondary">
          Layers
        </Typography>
      )}

      {mapDetailTab === "layers" || warehouseMapId == null ? (
        <>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {(
              [
                ...MAP_INSPECTION_LAYER_KEYS,
                "dronePath",
                "grid",
              ] as LiveMapLayerKey[]
            ).map((key) => {
              const hasData = layerHasStoredChunks(
                key,
                state.chunks,
                state.manifest,
              );
              const captureUnavailable = LAYER_CAPTURE_UNAVAILABLE[key];
              const disabled =
                key !== "dronePath" && key !== "grid" && !hasData;
              const helper = !hasData
                ? captureUnavailable ??
                  (key === "mid360LiDAR"
                    ? "No Mid360 chunks in this saved scan. Re-run the flight after the latest backend update, or enable WAREHOUSE_LIVE_MAP_RAW_LIDAR_ENABLED before scanning."
                    : "No stored chunks for this layer in the selected scan.")
                : null;
              const label = `${LIVE_MAP_LAYER_LABELS[key]}${
                hasData && key !== "dronePath" && key !== "grid"
                  ? ` (${chunksByLayer[key]})`
                  : ""
              }`;

              return (
                <FormControlLabel
                  key={key}
                  control={
                    <Checkbox
                      size="small"
                      checked={layers[key]}
                      disabled={disabled}
                      onChange={() => updateLayer(key)}
                    />
                  }
                  label={label}
                  title={helper ?? undefined}
                />
              );
            })}
          </Stack>

          <Stack spacing={0.75}>
            <Typography variant="caption" color="text.secondary">
              Max points per layer
            </Typography>
            {MAP_INSPECTION_LAYER_KEYS.map((key) => (
              <WarehouseLayerBudgetSlider
                key={key}
                label={LIVE_MAP_LAYER_LABELS[key]}
                value={layerPointBudget[key]}
                onCommit={(value) => updateBudget(key, value)}
              />
            ))}
          </Stack>
        </>
      ) : mapPlacementPanel && onCoordinateSetupError ? (
        <WarehouseCoordinateSetupPanel
          warehouseMapId={warehouseMapId}
          token={coordinateSetupToken}
          onError={onCoordinateSetupError}
          mapPlacement={mapPlacementPanel}
          structure={structure.structure}
          extractionStatus={structure.extractionStatus}
          autoDetecting={structure.extracting}
          structureLoading={structure.loading}
          structureError={structure.error}
          onAutoDetect={structure.extract}
          provisionalCandidates={state.provisionalCandidates}
          coverageRepairHints={state.coverageRepairHints}
          coordinateState={state.coordinateState}
        />
      ) : null}
    </Stack>
  );
}
