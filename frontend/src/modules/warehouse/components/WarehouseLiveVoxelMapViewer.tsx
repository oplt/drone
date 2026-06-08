import { useMemo, useState } from "react";
import { Box, Checkbox, FormControlLabel, Stack } from "@mui/material";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import { useLiveMapChunkCache } from "../hooks/useLiveMapChunkCache";
import {
  WarehouseLiveVoxelScene,
  type LiveVoxelLayers,
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

export function WarehouseLiveVoxelMapViewer({
  state,
  hidden = false,
  mappingStatus = null,
  mappingStackStatus = null,
  cacheMode,
}: {
  state: WarehouseLiveVoxelMapState;
  hidden?: boolean;
  mappingStatus?: WarehouseMappingRuntimeStatus | null;
  mappingStackStatus?: WarehouseMappingStackStatus | null;
  cacheMode?: "live" | "replay";
}) {
  const [layers, setLayers] = useState<LiveVoxelLayers>({
    mesh: true,
    pointCloud: true,
    scanPath: true,
    footprint: true,
    drone: true,
  });
  const resolvedCacheMode =
    cacheMode ?? (state.connectionState === "finalized" ? "replay" : "live");
  const cachedChunks = useLiveMapChunkCache(state.chunks, state.token, {
    mode: resolvedCacheMode,
  });
  const cachedBytes = useMemo(
    () => cachedChunks.reduce((sum, entry) => sum + entry.bytes, 0),
    [cachedChunks],
  );

  const updateLayer = (key: keyof LiveVoxelLayers) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  };

  return (
    <Stack spacing={1.25}>
      <WarehouseLiveVoxelHeader state={state} cachedBytes={cachedBytes} />
      <WarehouseMappingHealthPanel
        status={mappingStatus}
        liveHealth={state.health}
        mappingStackStatus={mappingStackStatus}
      />

      <WarehouseLiveVoxelMetrics
        state={state}
        mappingStackStatus={mappingStackStatus}
      />

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
              />
          )}
        {["empty", "connecting", "reconnecting", "stale", "failed"].includes(
          state.connectionState,
        ) && <WarehouseLiveVoxelOverlay state={state} />}
      </Box>

      <WarehouseLiveVoxelHealthChips state={state} />

      <Stack direction="row" spacing={1} flexWrap="wrap">
        {(
          ["mesh", "pointCloud", "scanPath", "footprint", "drone"] as const
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
            label={key.replace(
              /[A-Z]/g,
              (letter) => ` ${letter.toLowerCase()}`,
            )}
          />
        ))}
      </Stack>
    </Stack>
  );
}
