import { Alert, Stack, Tab, Tabs, Typography } from "@mui/material";
import { WarehouseCoordinateSetupPanel } from "./WarehouseCoordinateSetupPanel";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import { useLiveMapChunkCache } from "../hooks/useLiveMapChunkCache";
import type { WarehouseMapPlacementPanelProps, WarehouseMapPlacementViewerProps } from "../hooks/useWarehouseMapPlacement";
import { useWarehouseStructure } from "../hooks/useWarehouseStructure";
import type { WarehouseMappingStackStatus } from "../api/warehouseMissionsApi";
import type { WarehouseMappingRuntimeStatus } from "./WarehouseMappingHealthPanel";
import { WarehouseLiveVoxelHealthChips } from "./WarehouseLiveVoxelStatus";
import { LiveVoxelViewerDiagnosticsDrawer, LiveVoxelViewerMapFrame } from "./liveVoxel/LiveVoxelViewerMapFrame";
import { LiveVoxelViewerLayerPanel, LiveVoxelViewerToolbar } from "./liveVoxel/LiveVoxelViewerPanels";
import { useLiveVoxelViewerModel } from "./liveVoxel/useLiveVoxelViewerModel";
import { useLiveVoxelViewerChunkStats } from "./liveVoxel/useLiveVoxelViewerChunkStats";

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
  const model = useLiveVoxelViewerModel(state, flightId, scannedMapId, cacheMode, mapPlacement);
  const structure = useWarehouseStructure(
    mapDetailTab === "coordinateSetup" ? warehouseMapId : null,
    coordinateSetupToken,
  );

  const {
    cachedChunks,
    downloadedChunkIds,
    inFlightChunkIds,
    droppedChunkCount,
    maxConcurrentDownloads,
  } = useLiveMapChunkCache(model.resolvedFlightId, state.chunks, state.token, {
    mode: model.resolvedCacheMode,
    visibleLayers: model.layers,
    config: model.liveMapConfig,
  });

  const chunkStats = useLiveVoxelViewerChunkStats(
    state,
    model.resolvedFlightId,
    model.layers,
    cachedChunks,
    downloadedChunkIds,
    inFlightChunkIds,
    model.layerPointBudget,
    model.pointsByLayer,
    droppedChunkCount,
    maxConcurrentDownloads,
  );

  return (
    <Stack spacing={1.25}>
      {model.configError ? (
        <Alert severity="warning">
          Live-map configuration could not be loaded. Safe display defaults are active.{" "}
          {model.configError}
        </Alert>
      ) : null}
      {model.rawLidarOnly ? (
        <Alert severity="warning">
          This saved map contains raw Mid360 LiDAR only. RGB-D or nvBlox colored layers were not
          available when the scan was finalized.
        </Alert>
      ) : null}

      <LiveVoxelViewerToolbar
        highDensity={model.highDensity}
        onHighDensityChange={model.setHighDensity}
        colorMode={model.colorMode}
        onColorModeChange={model.setColorMode}
        pointSize={model.pointSize}
        onPointSizeChange={model.setPointSize}
        onOpenDiagnostics={() => model.setDiagnosticsOpen(true)}
        onReloadReplay={onReloadReplay}
        onToggleStream={onToggleStream}
        onClearMap={onClearMap}
        streamPaused={streamPaused}
      />

      <LiveVoxelViewerMapFrame
        state={state}
        hidden={hidden}
        layers={model.layers}
        cachedChunks={cachedChunks}
        renderOptions={model.renderOptions}
        mapPlacement={model.effectiveMapPlacement}
        structure={
          structure.structure?.status === "ready" ? structure.structure.summary : null
        }
        scenePickBlockReason={model.scenePickBlockReason}
        visiblePointTotal={chunkStats.visiblePointTotal}
        replayLoading={replayLoading}
      />

      <WarehouseLiveVoxelHealthChips state={state} />

      {warehouseMapId != null ? (
        <Tabs
          value={mapDetailTab}
          onChange={(_, value: "layers" | "coordinateSetup") => onMapDetailTabChange?.(value)}
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
        <LiveVoxelViewerLayerPanel
          state={state}
          layers={model.layers}
          layerPointBudget={model.layerPointBudget}
          chunksByLayer={model.chunksByLayer}
          highDensity={model.highDensity}
          maxPointsPerLayer={model.liveMapConfig.frontend.max_points_per_layer}
          onToggleLayer={model.updateLayer}
          onBudgetCommit={model.updateBudget}
        />
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

      <LiveVoxelViewerDiagnosticsDrawer
        open={model.diagnosticsOpen}
        onClose={() => model.setDiagnosticsOpen(false)}
        state={state}
        mappingStatus={mappingStatus}
        mappingStackStatus={mappingStackStatus}
        cachedBytes={chunkStats.cachedBytes}
        streamPaused={streamPaused}
        pointsByLayer={model.pointsByLayer}
        renderStats={chunkStats.renderStats}
        mapMode={mapMode}
        flightId={flightId}
        scannedMapId={scannedMapId}
        cachedChunkCount={cachedChunks.length}
        manifestChunkTotal={model.manifestChunkTotal}
        visiblePointTotal={chunkStats.visiblePointTotal}
        manifestPointTotal={model.manifestPointTotal}
        downloadedChunkCount={downloadedChunkIds.size}
        inFlightChunkCount={inFlightChunkIds.size}
        visiblePendingChunkCount={chunkStats.visiblePendingChunkCount}
      />
    </Stack>
  );
}
