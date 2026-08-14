import type {
  WarehouseCoordinateLiveState,
  WarehouseCoverageRepairHint,
  WarehouseLiveHealthFlags,
  WarehouseLiveMapManifestSummary,
  WarehouseLiveMapMessage,
  WarehouseLiveMapUpdate,
  WarehouseLiveProvisionalCandidate,
  WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";
import {
  applyWarehouseLiveMapMessage,
  mergeUpdate,
} from "./liveMapUpdateMerge";
import {
  isWarehouseLiveMapSnapshot,
  isWarehouseLiveMapUpdate,
} from "../api/warehouseLiveMapApi";

import type { WarehouseLiveVoxelConnectionState } from "./warehouseLiveVoxelMapConstants";

export type WarehouseLiveVoxelMergedState = {
  chunksById: Map<string, WarehouseLiveVoxelChunk>;
  provisionalCandidatesByKey: Map<string, WarehouseLiveProvisionalCandidate>;
  coverageRepairHints: WarehouseCoverageRepairHint[];
  coordinateState: WarehouseCoordinateLiveState | null;
  scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  flightId: string | null;
};

export type WarehouseLiveVoxelBatchResult = {
  merged: WarehouseLiveVoxelMergedState;
  newestUpdate: WarehouseLiveMapUpdate | null;
  newestSnapshotStatus: WarehouseLiveVoxelConnectionState | null;
  newestLastUpdateAt: string | null;
  finalizedId: number | null;
  newestManifest: WarehouseLiveMapManifestSummary | null;
};

export function applyWarehouseLiveVoxelMessageBatch(
  current: WarehouseLiveVoxelMergedState,
  messages: WarehouseLiveMapMessage[],
): WarehouseLiveVoxelBatchResult {
  let merged = current;
  let newestUpdate: WarehouseLiveMapUpdate | null = null;
  let newestSnapshotStatus: WarehouseLiveVoxelConnectionState | null = null;
  let newestLastUpdateAt: string | null = null;
  let finalizedId: number | null = null;
  let newestManifest: WarehouseLiveMapManifestSummary | null = null;

  for (const queued of messages) {
    if (isWarehouseLiveMapSnapshot(queued)) {
      merged = applyWarehouseLiveMapMessage(merged, queued);
      newestUpdate = queued.updates.at(-1) ?? newestUpdate;
      newestSnapshotStatus =
        queued.status === "empty" ? "connecting" : queued.status;
      newestLastUpdateAt =
        queued.last_update_at ?? newestUpdate?.timestamp ?? newestLastUpdateAt;
      if (queued.manifest) {
        newestManifest = queued.manifest;
      }
      continue;
    }

    if (isWarehouseLiveMapUpdate(queued)) {
      merged = mergeUpdate(merged, queued);
      newestUpdate = queued;
      newestLastUpdateAt = queued.timestamp ?? newestLastUpdateAt;
      newestSnapshotStatus = "live";
      continue;
    }

    if (queued.type === "live_map_finalized") {
      finalizedId = queued.finalized_scan_job_id;
      newestLastUpdateAt = queued.last_update_at ?? newestLastUpdateAt;
      newestSnapshotStatus = "finalized";
    }
  }

  return {
    merged,
    newestUpdate,
    newestSnapshotStatus,
    newestLastUpdateAt,
    finalizedId,
    newestManifest,
  };
}

export function emptyWarehouseLiveVoxelMergedState(
  flightId: string | null = null,
): WarehouseLiveVoxelMergedState {
  return {
    chunksById: new Map<string, WarehouseLiveVoxelChunk>(),
    provisionalCandidatesByKey: new Map<string, WarehouseLiveProvisionalCandidate>(),
    coverageRepairHints: [],
    coordinateState: null,
    scanPath: [],
    flightId,
  };
}

export type WarehouseLiveVoxelMapState = {
  connectionState: WarehouseLiveVoxelConnectionState;
  chunks: WarehouseLiveVoxelChunk[];
  provisionalCandidates: WarehouseLiveProvisionalCandidate[];
  coverageRepairHints: WarehouseCoverageRepairHint[];
  coordinateState: WarehouseCoordinateLiveState | null;
  latestUpdate: WarehouseLiveMapUpdate | null;
  health: WarehouseLiveHealthFlags;
  scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  error: string | null;
  finalizedScanJobId: number | null;
  lastUpdateAt: string | null;
  manifest: WarehouseLiveMapManifestSummary | null;
  token?: string | null;
};

export type WarehouseLiveVoxelMapControls = {
  clearMap: () => void;
  streamPaused: boolean;
  setStreamPaused: (paused: boolean) => void;
  toggleStreamPaused: () => void;
};
