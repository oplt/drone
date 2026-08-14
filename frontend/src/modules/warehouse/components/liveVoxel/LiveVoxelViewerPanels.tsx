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
  Switch,
  Typography,
} from "@mui/material";
import { WarehouseLayerBudgetSlider } from "../WarehouseLayerBudgetSlider";
import type { WarehouseLiveVoxelMapState } from "../../hooks/useWarehouseLiveVoxelMap";
import {
  LAYER_CAPTURE_UNAVAILABLE,
  LIVE_MAP_LAYER_LABELS,
  MAP_INSPECTION_LAYER_KEYS,
  layerHasStoredChunks,
  type LiveMapColorMode,
  type LiveMapLayerKey,
} from "../../utils/liveMapLayerUtils";
import type { LiveVoxelLayers } from "./scene/liveVoxelSceneTypes";

type LiveVoxelViewerToolbarProps = {
  highDensity: boolean;
  onHighDensityChange: (checked: boolean) => void;
  colorMode: LiveMapColorMode;
  onColorModeChange: (mode: LiveMapColorMode) => void;
  pointSize: number;
  onPointSizeChange: (value: number) => void;
  onOpenDiagnostics: () => void;
  onReloadReplay?: () => void;
  onToggleStream?: () => void;
  onClearMap?: () => void;
  streamPaused?: boolean;
};

export function LiveVoxelViewerToolbar({
  highDensity,
  onHighDensityChange,
  colorMode,
  onColorModeChange,
  pointSize,
  onPointSizeChange,
  onOpenDiagnostics,
  onReloadReplay,
  onToggleStream,
  onClearMap,
  streamPaused = false,
}: LiveVoxelViewerToolbarProps) {
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
      <Button size="small" variant="outlined" onClick={onOpenDiagnostics}>
        Diagnostics
      </Button>
      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={highDensity}
            onChange={(_event, checked) => onHighDensityChange(checked)}
          />
        }
        label="High density"
      />
      {onReloadReplay ? (
        <Button size="small" variant="outlined" onClick={onReloadReplay}>
          Refresh map from disk
        </Button>
      ) : null}
      {onToggleStream ? (
        <Button size="small" variant="outlined" onClick={onToggleStream}>
          {streamPaused ? "Resume stream" : "Pause stream"}
        </Button>
      ) : null}
      {onClearMap ? (
        <Button size="small" variant="outlined" onClick={onClearMap}>
          Clear accumulated map
        </Button>
      ) : null}
      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="live-map-color-mode">Color mode</InputLabel>
        <Select
          labelId="live-map-color-mode"
          label="Color mode"
          value={colorMode}
          onChange={(event) => onColorModeChange(event.target.value as LiveMapColorMode)}
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
          onChange={(_event, value) => onPointSizeChange(Number(value))}
        />
      </Box>
    </Stack>
  );
}

type LiveVoxelViewerLayerPanelProps = {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
  layerPointBudget: Record<LiveMapLayerKey, number>;
  chunksByLayer: Record<LiveMapLayerKey, number>;
  highDensity: boolean;
  maxPointsPerLayer: number;
  onToggleLayer: (key: LiveMapLayerKey) => void;
  onBudgetCommit: (key: LiveMapLayerKey, value: number) => void;
};

export function LiveVoxelViewerLayerPanel({
  state,
  layers,
  layerPointBudget,
  chunksByLayer,
  highDensity,
  maxPointsPerLayer,
  onToggleLayer,
  onBudgetCommit,
}: LiveVoxelViewerLayerPanelProps) {
  return (
    <>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        {([...MAP_INSPECTION_LAYER_KEYS, "dronePath", "grid"] as LiveMapLayerKey[]).map(
          (key) => {
            const hasData = layerHasStoredChunks(key, state.chunks, state.manifest);
            const captureUnavailable = LAYER_CAPTURE_UNAVAILABLE[key];
            const disabled = key !== "dronePath" && key !== "grid" && !hasData;
            const helper = !hasData
              ? (captureUnavailable ??
                (key === "mid360LiDAR"
                  ? "No Mid360 chunks in this saved scan. Re-run the flight after the latest backend update, or enable WAREHOUSE_LIVE_MAP_RAW_LIDAR_ENABLED before scanning."
                  : "No stored chunks for this layer in the selected scan."))
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
                    onChange={() => onToggleLayer(key)}
                  />
                }
                label={label}
                title={helper ?? undefined}
              />
            );
          },
        )}
      </Stack>

      <Stack spacing={0.75}>
        <Typography variant="caption" color="text.secondary">
          Max points per layer
          {highDensity
            ? ` (high density up to ${maxPointsPerLayer.toLocaleString()})`
            : " (safe defaults — enable High density for config max)"}
        </Typography>
        {MAP_INSPECTION_LAYER_KEYS.map((key) => (
          <WarehouseLayerBudgetSlider
            key={key}
            label={LIVE_MAP_LAYER_LABELS[key]}
            value={layerPointBudget[key]}
            onCommit={(value) => onBudgetCommit(key, value)}
          />
        ))}
      </Stack>
    </>
  );
}
