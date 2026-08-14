import { useEffect, useMemo, useRef, useState } from "react";
import type {
  WarehouseCoordinateLiveState,
  WarehouseCoverageRepairHint,
  WarehouseLiveHealthFlags,
  WarehouseLiveMapManifestSummary,
  WarehouseLiveMapUpdate,
  WarehouseLiveProvisionalCandidate,
  WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";
import { useWarehouseLiveVoxelMapTransport } from "./useWarehouseLiveVoxelMapTransport";
import {
  emptyWarehouseLiveVoxelMergedState,
  type WarehouseLiveVoxelMapControls,
  type WarehouseLiveVoxelMapState,
  type WarehouseLiveVoxelMergedState,
} from "../utils/warehouseLiveVoxelMapTypes";
import {
  WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH,
  type WarehouseLiveVoxelConnectionState,
} from "../utils/warehouseLiveVoxelMapConstants";

export type {
  WarehouseLiveVoxelMapControls,
  WarehouseLiveVoxelMapState,
} from "../utils/warehouseLiveVoxelMapTypes";

export {
  warehouseLiveMapReconnectDelayMs,
  warehouseLiveMapSnapshotPollDelayMs,
} from "../utils/warehouseLiveVoxelMapTiming";

export function useWarehouseLiveVoxelMap(
  flightId: string | null | undefined,
  options: {
    enabled?: boolean;
    token?: string | null;
  } = {},
): WarehouseLiveVoxelMapState & WarehouseLiveVoxelMapControls {
  const enabled = options.enabled ?? true;
  const [streamPaused, setStreamPaused] = useState(false);
  const streamPausedRef = useRef(streamPaused);
  const [connectionState, setConnectionState] =
    useState<WarehouseLiveVoxelConnectionState>("empty");
  const [chunksById, setChunksById] = useState(
    new Map<string, WarehouseLiveVoxelChunk>(),
  );
  const [provisionalCandidatesByKey, setProvisionalCandidatesByKey] = useState(
    new Map<string, WarehouseLiveProvisionalCandidate>(),
  );
  const [coverageRepairHints, setCoverageRepairHints] = useState<
    WarehouseCoverageRepairHint[]
  >([]);
  const [coordinateState, setCoordinateState] =
    useState<WarehouseCoordinateLiveState | null>(null);
  const [scanPath, setScanPath] = useState<
    WarehouseLiveMapUpdate["scan_path_sample"]
  >([]);
  const [latestUpdate, setLatestUpdate] =
    useState<WarehouseLiveMapUpdate | null>(null);
  const [health, setHealth] = useState<WarehouseLiveHealthFlags>(
    WAREHOUSE_LIVE_VOXEL_EMPTY_HEALTH,
  );
  const [error, setError] = useState<string | null>(null);
  const [finalizedScanJobId, setFinalizedScanJobId] = useState<number | null>(
    null,
  );
  const [lastUpdateAt, setLastUpdateAt] = useState<string | null>(null);
  const [manifest, setManifest] = useState<WarehouseLiveMapManifestSummary | null>(
    null,
  );

  const stateRef = useRef<WarehouseLiveVoxelMergedState>(
    emptyWarehouseLiveVoxelMergedState(flightId ?? null),
  );

  useEffect(() => {
    streamPausedRef.current = streamPaused;
  }, [streamPaused]);

  useEffect(() => {
    stateRef.current = {
      chunksById,
      provisionalCandidatesByKey,
      coverageRepairHints,
      coordinateState,
      scanPath,
      flightId: flightId ?? null,
    };
  }, [
    chunksById,
    coordinateState,
    coverageRepairHints,
    flightId,
    provisionalCandidatesByKey,
    scanPath,
  ]);

  const setters = useMemo(
    () => ({
      setConnectionState,
      setChunksById,
      setProvisionalCandidatesByKey,
      setCoverageRepairHints,
      setCoordinateState,
      setScanPath,
      setLatestUpdate,
      setHealth,
      setError,
      setFinalizedScanJobId,
      setLastUpdateAt,
      setManifest,
    }),
    [],
  );

  useWarehouseLiveVoxelMapTransport({
    flightId,
    enabled,
    token: options.token,
    streamPausedRef,
    stateRef,
    setters,
  });

  const chunks = useMemo(() => Array.from(chunksById.values()), [chunksById]);
  const provisionalCandidates = useMemo(
    () => Array.from(provisionalCandidatesByKey.values()),
    [provisionalCandidatesByKey],
  );

  const clearMap = () => {
    const empty = emptyWarehouseLiveVoxelMergedState(null);
    stateRef.current = empty;
    setChunksById(empty.chunksById);
    setProvisionalCandidatesByKey(empty.provisionalCandidatesByKey);
    setCoverageRepairHints(empty.coverageRepairHints);
    setCoordinateState(empty.coordinateState);
    setScanPath(empty.scanPath);
    setLatestUpdate(null);
    setManifest(null);
  };

  const toggleStreamPaused = () => {
    setStreamPaused((current) => !current);
  };

  return {
    connectionState,
    chunks,
    provisionalCandidates,
    coverageRepairHints,
    coordinateState,
    latestUpdate,
    health,
    scanPath,
    error,
    finalizedScanJobId,
    lastUpdateAt,
    manifest,
    token: options.token,
    clearMap,
    streamPaused,
    setStreamPaused,
    toggleStreamPaused,
  };
}
