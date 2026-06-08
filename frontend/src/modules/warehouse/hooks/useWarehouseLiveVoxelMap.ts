import { useEffect, useMemo, useRef, useState } from "react";
import {
  connectWarehouseLiveMap,
  disconnectWarehouseLiveMap,
  fetchWarehouseLiveMapSnapshot,
  isWarehouseLiveMapSnapshot,
  isWarehouseLiveMapUpdate,
  type WarehouseLiveHealthFlags,
  type WarehouseLiveMapMessage,
  type WarehouseLiveMapUpdate,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

type ConnectionState =
  | "empty"
  | "connecting"
  | "live"
  | "stale"
  | "reconnecting"
  | "finalized"
  | "failed";

const STALE_AFTER_MS = 10_000;
const RECONNECT_AFTER_MS = 1_500;
const MAX_CHUNKS = 160;
const MAX_PATH_POINTS = 600;

const EMPTY_HEALTH: WarehouseLiveHealthFlags = {
  coverage_percent: null,
  drift_estimate_m: null,
  stale_costmap: false,
  missing_mesh: true,
  missing_point_cloud: true,
  nvblox_ready: false,
  mapping_recording: false,
  stack_running: false,
};

export type WarehouseLiveVoxelMapState = {
  connectionState: ConnectionState;
  chunks: WarehouseLiveVoxelChunk[];
  latestUpdate: WarehouseLiveMapUpdate | null;
  health: WarehouseLiveHealthFlags;
  scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  error: string | null;
  finalizedScanJobId: number | null;
  lastUpdateAt: string | null;
  token?: string | null;
};

function mergeUpdate(
  current: {
    chunksById: Map<string, WarehouseLiveVoxelChunk>;
    scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  },
  update: WarehouseLiveMapUpdate,
) {
  const chunksById = new Map(current.chunksById);
  for (const id of update.removed_chunk_ids) {
    chunksById.delete(id);
  }
  for (const chunk of update.changed_chunks) {
    chunksById.set(chunk.id, chunk);
  }
  const chunks = Array.from(chunksById.values())
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
    .slice(-MAX_CHUNKS);
  const nextChunksById = new Map(chunks.map((chunk) => [chunk.id, chunk]));
  const scanPath = [...current.scanPath, ...update.scan_path_sample].slice(
    -MAX_PATH_POINTS,
  );
  return { chunksById: nextChunksById, scanPath };
}

export function applyWarehouseLiveMapMessage(
  current: {
    chunksById: Map<string, WarehouseLiveVoxelChunk>;
    scanPath: WarehouseLiveMapUpdate["scan_path_sample"];
  },
  message: WarehouseLiveMapMessage,
) {
  if (isWarehouseLiveMapSnapshot(message)) {
    return message.updates.reduce(mergeUpdate, {
      chunksById: new Map<string, WarehouseLiveVoxelChunk>(),
      scanPath: [],
    });
  }
  if (isWarehouseLiveMapUpdate(message)) {
    return mergeUpdate(current, message);
  }
  return current;
}

export function useWarehouseLiveVoxelMap(
  flightId: string | null | undefined,
  options: {
    enabled?: boolean;
    token?: string | null;
  } = {},
): WarehouseLiveVoxelMapState {
  const enabled = options.enabled ?? true;
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("empty");
  const [chunksById, setChunksById] = useState(
    new Map<string, WarehouseLiveVoxelChunk>(),
  );
  const [scanPath, setScanPath] = useState<
    WarehouseLiveMapUpdate["scan_path_sample"]
  >([]);
  const [latestUpdate, setLatestUpdate] =
    useState<WarehouseLiveMapUpdate | null>(null);
  const [health, setHealth] = useState<WarehouseLiveHealthFlags>(EMPTY_HEALTH);
  const [error, setError] = useState<string | null>(null);
  const [finalizedScanJobId, setFinalizedScanJobId] = useState<number | null>(
    null,
  );
  const [lastUpdateAt, setLastUpdateAt] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const stateRef = useRef({
    chunksById: new Map<string, WarehouseLiveVoxelChunk>(),
    scanPath: [] as WarehouseLiveMapUpdate["scan_path_sample"],
  });
  const reconnectTimerRef = useRef<number | null>(null);
  const staleTimerRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const queuedMessageRef = useRef<WarehouseLiveMapMessage[]>([]);

  useEffect(() => {
    stateRef.current = { chunksById, scanPath };
  }, [chunksById, scanPath]);

  useEffect(() => {
    if (!flightId || typeof window === "undefined") {
      setConnectionState("empty");
      setChunksById(new Map());
      setScanPath([]);
      setLatestUpdate(null);
      setHealth(EMPTY_HEALTH);
      setError(null);
      setFinalizedScanJobId(null);
      setLastUpdateAt(null);
      return;
    }
    if (!enabled) {
      disconnectWarehouseLiveMap(socketRef.current);
      socketRef.current = null;
      setConnectionState((current) => (current === "live" ? "stale" : current));
      return;
    }

    let cancelled = false;
    let reconnectAttempt = 0;

    const clearTimers = () => {
      if (reconnectTimerRef.current != null)
        window.clearTimeout(reconnectTimerRef.current);
      if (staleTimerRef.current != null)
        window.clearTimeout(staleTimerRef.current);
      if (rafRef.current != null) window.cancelAnimationFrame(rafRef.current);
      reconnectTimerRef.current = null;
      staleTimerRef.current = null;
      rafRef.current = null;
    };

    const scheduleStaleCheck = () => {
      if (staleTimerRef.current != null)
        window.clearTimeout(staleTimerRef.current);
      staleTimerRef.current = window.setTimeout(() => {
        setConnectionState((current) =>
          current === "live" ? "stale" : current,
        );
      }, STALE_AFTER_MS);
    };

    const applyMessage = (message: WarehouseLiveMapMessage) => {
      queuedMessageRef.current.push(message);

      if (rafRef.current != null) return;

      rafRef.current = window.requestAnimationFrame(() => {
        rafRef.current = null;

        const queuedMessages = queuedMessageRef.current;
        queuedMessageRef.current = [];

        if (queuedMessages.length === 0) return;

        let merged = stateRef.current;
        let newestUpdate: WarehouseLiveMapUpdate | null = null;
        let newestSnapshotStatus: ConnectionState | null = null;
        let newestLastUpdateAt: string | null = null;
        let finalizedId: number | null = null;

        for (const queued of queuedMessages) {
          if (isWarehouseLiveMapSnapshot(queued)) {
            merged = applyWarehouseLiveMapMessage(merged, queued);
            newestUpdate = queued.updates.at(-1) ?? newestUpdate;
            newestSnapshotStatus =
                queued.status === "empty" ? "connecting" : queued.status;
            newestLastUpdateAt =
                queued.last_update_at ?? newestUpdate?.timestamp ?? newestLastUpdateAt;
            continue;
          }

          if (isWarehouseLiveMapUpdate(queued)) {
            merged = applyWarehouseLiveMapMessage(merged, queued);
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

        stateRef.current = merged;
        setChunksById(merged.chunksById);
        setScanPath(merged.scanPath);

        if (newestUpdate) {
          setLatestUpdate(newestUpdate);
          setHealth(newestUpdate.health ?? EMPTY_HEALTH);
        }

        if (newestLastUpdateAt) {
          setLastUpdateAt(newestLastUpdateAt);
        }

        if (finalizedId != null) {
          setFinalizedScanJobId(finalizedId);
        }

        if (newestSnapshotStatus) {
          setConnectionState(newestSnapshotStatus);
        }

        scheduleStaleCheck();
      });
    };

    const openSocket = () => {
      if (cancelled) return;
      setConnectionState(reconnectAttempt > 0 ? "reconnecting" : "connecting");
      socketRef.current = connectWarehouseLiveMap(
        flightId,
        {
          onOpen: () => {
            reconnectAttempt = 0;
            setError(null);
            setConnectionState("live");
            scheduleStaleCheck();
            if (socketRef.current?.readyState === WebSocket.OPEN) {
              socketRef.current.send(JSON.stringify({ type: "ping" }));
            }
          },
          onMessage: applyMessage,
          onError: () => {
            setError("Live voxel stream error.");
          },
            onClose: () => {
            if (cancelled) return;
            reconnectAttempt += 1;
            setConnectionState((current) =>
              current === "finalized" ? current : "reconnecting",
            );
            reconnectTimerRef.current = window.setTimeout(
              openSocket,
              RECONNECT_AFTER_MS,
            );
          },
        },
        options.token,
      );
    };

    const pollSnapshot = () => {
      void fetchWarehouseLiveMapSnapshot(flightId, options.token)
        .then((snapshot) => {
          if (!cancelled) applyMessage(snapshot);
        })
        .catch(() => {
          /* keep websocket path; snapshot is a bootstrap fallback */
        });
    };

    void fetchWarehouseLiveMapSnapshot(flightId, options.token)
      .then((snapshot) => {
        if (!cancelled) applyMessage(snapshot);
      })
      .catch(() => {
        if (!cancelled) setError("Live voxel snapshot could not be loaded.");
      });

    openSocket();
    const snapshotPoll = window.setInterval(pollSnapshot, 3000);

    return () => {
      window.clearInterval(snapshotPoll);
      cancelled = true;
      clearTimers();
      disconnectWarehouseLiveMap(socketRef.current);
      socketRef.current = null;
    };
  }, [enabled, flightId, options.token]);

  const chunks = useMemo(() => Array.from(chunksById.values()), [chunksById]);

  return {
    connectionState,
    chunks,
    latestUpdate,
    health,
    scanPath,
    error,
    finalizedScanJobId,
    lastUpdateAt,
    token: options.token,
  };
}
