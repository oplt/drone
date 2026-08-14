import { Alert, Box, Button, CircularProgress, Drawer, Stack, Typography } from "@mui/material";
import type { WarehouseLiveVoxelMapState } from "../../hooks/useWarehouseLiveVoxelMap";
import type { WarehouseMappingStackStatus } from "../../api/warehouseMissionsApi";
import type { LiveMapLayerKey } from "../../utils/liveMapLayerUtils";
import {
  WarehouseMappingHealthPanel,
  type WarehouseMappingRuntimeStatus,
} from "../WarehouseMappingHealthPanel";
import {
  WarehouseLiveVoxelHeader,
  WarehouseLiveVoxelMetrics,
  WarehouseLiveVoxelOverlay,
} from "../WarehouseLiveVoxelStatus";
import { WarehouseLiveVoxelScene } from "../WarehouseLiveVoxelScene";
import type { WarehouseMapPlacementViewerProps } from "../../hooks/useWarehouseMapPlacement";
import type { WarehouseStructureSummary } from "../../api/warehouseInspectionApi";
import type { CachedLiveMapChunk } from "../../hooks/useLiveMapChunkCache";
import type { LiveVoxelLayers, LiveVoxelRenderOptions } from "./scene/liveVoxelSceneTypes";

type LiveVoxelViewerMapFrameProps = {
  state: WarehouseLiveVoxelMapState;
  hidden: boolean;
  layers: LiveVoxelLayers;
  cachedChunks: CachedLiveMapChunk[];
  renderOptions: LiveVoxelRenderOptions;
  mapPlacement: WarehouseMapPlacementViewerProps | null;
  structure: WarehouseStructureSummary | null;
  scenePickBlockReason: string | null;
  visiblePointTotal: number;
  replayLoading: boolean;
};

export function LiveVoxelViewerMapFrame({
  state,
  hidden,
  layers,
  cachedChunks,
  renderOptions,
  mapPlacement,
  structure,
  scenePickBlockReason,
  visiblePointTotal,
  replayLoading,
}: LiveVoxelViewerMapFrameProps) {
  return (
    <Box
      sx={{
        borderRadius: 1,
        overflow: "hidden",
        border: "1px solid",
        borderColor: "divider",
        position: "relative",
        cursor: mapPlacement?.pickMode && !scenePickBlockReason ? "crosshair" : "default",
      }}
      role="img"
      aria-label="Interactive warehouse voxel map"
      aria-describedby="warehouse-voxel-map-description"
      tabIndex={0}
    >
      <Typography
        id="warehouse-voxel-map-description"
        component="span"
        sx={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}
      >
        {state.chunks.length} chunks and {visiblePointTotal.toLocaleString()} loaded points. Use mouse
        or touch to orbit, pan, and zoom. Layer visibility and point budgets are listed below.
      </Typography>
      {!hidden ? (
        <WarehouseLiveVoxelScene
          state={state}
          layers={layers}
          cachedChunks={cachedChunks}
          renderOptions={renderOptions}
          mapPlacement={mapPlacement}
          structure={structure}
        />
      ) : null}
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
      ) &&
        !replayLoading && <WarehouseLiveVoxelOverlay state={state} />}
    </Box>
  );
}

type LiveVoxelViewerDiagnosticsDrawerProps = {
  open: boolean;
  onClose: () => void;
  state: WarehouseLiveVoxelMapState;
  mappingStatus: WarehouseMappingRuntimeStatus | null;
  mappingStackStatus: WarehouseMappingStackStatus | null;
  cachedBytes: number;
  streamPaused: boolean;
  pointsByLayer: Record<LiveMapLayerKey, number>;
  renderStats: {
    renderedPointEstimate: number;
    pointBudget: number;
    droppedChunkCount: number;
    maxConcurrentDownloads: number;
  };
  mapMode: "live" | "replay";
  flightId: string | null;
  scannedMapId: number | null;
  cachedChunkCount: number;
  manifestChunkTotal: number;
  visiblePointTotal: number;
  manifestPointTotal: number;
  downloadedChunkCount: number;
  inFlightChunkCount: number;
  visiblePendingChunkCount: number;
};

export function LiveVoxelViewerDiagnosticsDrawer({
  open,
  onClose,
  state,
  mappingStatus,
  mappingStackStatus,
  cachedBytes,
  streamPaused,
  pointsByLayer,
  renderStats,
  mapMode,
  flightId,
  scannedMapId,
  cachedChunkCount,
  manifestChunkTotal,
  visiblePointTotal,
  manifestPointTotal,
  downloadedChunkCount,
  inFlightChunkCount,
  visiblePendingChunkCount,
}: LiveVoxelViewerDiagnosticsDrawerProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 2 } }}
    >
      <Stack spacing={1.25}>
        <Typography variant="h6">Map diagnostics</Typography>
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
          renderStats={renderStats}
        />
        <Typography variant="caption" color="text.secondary">
          Mode: {mapMode} · flight: {flightId ?? state.latestUpdate?.flight_id ?? "—"}
          {scannedMapId != null ? ` · scan #${scannedMapId}` : ""} · manifest:{" "}
          {state.manifest ? "disk" : "live"} · chunks {cachedChunkCount}/
          {manifestChunkTotal || state.chunks.length} loaded · points{" "}
          {visiblePointTotal.toLocaleString()}/{manifestPointTotal.toLocaleString()} visible
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Downloads: {downloadedChunkCount} complete, {inFlightChunkCount} in flight
          {visiblePendingChunkCount > 0
            ? ` · ${visiblePendingChunkCount} visible chunk(s) queued`
            : ""}
        </Typography>
        <Button onClick={onClose}>Close</Button>
      </Stack>
    </Drawer>
  );
}
