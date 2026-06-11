import { useEffect, useMemo, useState } from "react";
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
  Typography,
} from "@mui/material";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import { useLiveMapChunkCache } from "../hooks/useLiveMapChunkCache";
import {
  fetchWarehouseLiveMapConfig,
} from "../api/warehouseLiveMapApi";
import {
  DEFAULT_LIVE_MAP_CONFIG,
  mergeLiveMapConfig,
} from "../config/liveMapConfig";
import {
  WarehouseLiveVoxelScene,
  type LiveVoxelLayers,
  type LiveVoxelRenderOptions,
} from "./WarehouseLiveVoxelScene";
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
  countPointsByLayer,
  DEFAULT_LAYER_POINT_BUDGET,
  DEFAULT_LAYER_VISIBILITY,
  defaultLayerVisibilityForChunks,
  isRawLidarOnlyMap,
  LIVE_MAP_LAYER_LABELS,
  type LiveMapColorMode,
  type LiveMapLayerKey,
} from "../utils/liveMapLayerUtils";

const POINT_CLOUD_LAYERS: LiveMapLayerKey[] = [
  "rgbdColored",
  "mid360LiDAR",
  "nvbloxColor",
  "nvbloxEsdf",
  "nvbloxTsdf",
  "nvbloxMesh",
];

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
}) {
  const [layers, setLayers] = useState<LiveVoxelLayers>(DEFAULT_LAYER_VISIBILITY);
  const [pointSize, setPointSize] = useState(0.035);
  const [colorMode, setColorMode] = useState<LiveMapColorMode>("rgb");
  const [layerPointBudget, setLayerPointBudget] = useState(
    DEFAULT_LAYER_POINT_BUDGET,
  );
  const [liveMapConfig, setLiveMapConfig] = useState(DEFAULT_LIVE_MAP_CONFIG);

  useEffect(() => {
    if (!state.token) return;
    void fetchWarehouseLiveMapConfig(state.token)
      .then((payload) => setLiveMapConfig(mergeLiveMapConfig(payload)))
      .catch(() => {
        /* keep frontend defaults */
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
    }));
  }, [liveMapConfig.frontend.max_points_per_layer]);

  useEffect(() => {
    if (state.chunks.length === 0) return;
    setLayers((current) => ({
      ...current,
      ...defaultLayerVisibilityForChunks(state.chunks),
    }));
  }, [state.connectionState, state.chunks.length]);

  const rawLidarOnly = useMemo(
    () => isRawLidarOnlyMap(state.chunks, state.manifest),
    [state.chunks, state.manifest],
  );

  const resolvedCacheMode =
    cacheMode ?? (state.connectionState === "finalized" ? "replay" : "live");
  const resolvedFlightId =
    flightId ?? state.latestUpdate?.flight_id ?? null;
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
      cachedChunks.reduce(
        (sum, chunk) => sum + (chunk.point_count ?? 0),
        0,
      ),
    [cachedChunks],
  );

  const renderOptions: LiveVoxelRenderOptions = useMemo(
    () => ({
      pointSize,
      colorMode,
      layerPointBudget,
    }),
    [colorMode, layerPointBudget, pointSize],
  );

  const updateLayer = (key: LiveMapLayerKey) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  };

  const updateBudget = (key: LiveMapLayerKey, value: number) => {
    setLayerPointBudget((current) => ({ ...current, [key]: value }));
  };

  return (
    <Stack spacing={1.25}>
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
      </Typography>

      <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
        {onReloadReplay && (
          <Button size="small" variant="outlined" onClick={onReloadReplay}>
            Reload full map from disk manifest
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
        }}
      >
          {!hidden && (
              <WarehouseLiveVoxelScene
                  state={state}
                  layers={layers}
                  cachedChunks={cachedChunks}
                  renderOptions={renderOptions}
              />
          )}
        {["empty", "connecting", "reconnecting", "stale", "failed"].includes(
          state.connectionState,
        ) && <WarehouseLiveVoxelOverlay state={state} />}
      </Box>

      <WarehouseLiveVoxelHealthChips state={state} />

      <Typography variant="subtitle2" color="text.secondary">
        Layers
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        {(
          [
            ...POINT_CLOUD_LAYERS,
            "dronePath",
            "grid",
          ] as LiveMapLayerKey[]
        ).map((key) => (
          <FormControlLabel
            key={key}
            control={
              <Checkbox
                size="small"
                checked={layers[key]}
                onChange={() => updateLayer(key)}
              />
            }
            label={LIVE_MAP_LAYER_LABELS[key]}
          />
        ))}
      </Stack>

      <Stack spacing={0.75}>
        <Typography variant="caption" color="text.secondary">
          Max points per layer
        </Typography>
        {POINT_CLOUD_LAYERS.map((key) => (
          <Stack key={key} direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" sx={{ minWidth: 160 }}>
              {LIVE_MAP_LAYER_LABELS[key]}
            </Typography>
            <Slider
              size="small"
              sx={{ flex: 1 }}
              min={10_000}
              max={250_000}
              step={10_000}
              value={layerPointBudget[key]}
              onChange={(_event, value) => updateBudget(key, Number(value))}
            />
            <Typography variant="caption" sx={{ minWidth: 72 }}>
              {(layerPointBudget[key] / 1000).toFixed(0)}k
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
