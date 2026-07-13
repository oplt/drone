import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  fetchWarehouseLiveChunk,
  fetchWarehouseLiveChunkBatched,
  clearLiveMapChunkFetchCache,
  LIVE_MAP_BATCH_MAX_CHUNKS,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";
import type { LiveVoxelLayers } from "../components/WarehouseLiveVoxelScene";
import {
  DEFAULT_LIVE_MAP_CONFIG,
  filterChunksForDownload,
  type LiveMapRuntimeConfig,
} from "../config/liveMapConfig";
import {
  chunkCacheKey,
  selectDownloadableChunksPerLayer,
} from "../utils/liveMapChunkRetention";
import { liveMapDebugLog } from "../utils/liveMapDebug";

const LIVE_MAX_CACHED_BYTES = 48 * 1024 * 1024;
const REPLAY_MAX_CACHED_BYTES = 1024 * 1024 * 1024;
const REPLAY_MAX_CACHED_CHUNKS = 4000;
const inFlightChunkFetches = new Map<string, Promise<ArrayBuffer>>();

type ChunkCacheFrameBatch = {
  entries: Map<string, CachedLiveMapChunk>;
  downloadedKeys: Set<string>;
  inFlightAdds: Set<string>;
  inFlightRemoves: Set<string>;
};

function emptyFrameBatch(): ChunkCacheFrameBatch {
  return {
    entries: new Map(),
    downloadedKeys: new Set(),
    inFlightAdds: new Set(),
    inFlightRemoves: new Set(),
  };
}

export type LiveMapChunkCacheMode = "live" | "replay";

export type CachedLiveMapChunkKind =
  | "mesh"
  | "point_cloud"
  | "occupancy"
  | "esdf"
  | "costmap";

export type CachedLiveMapChunk = {
  cacheKey: string;
  id: string;
  kind: CachedLiveMapChunkKind;
  url: string;
  bytes: number;
  loaded: boolean;
  arrayBuffer: ArrayBuffer;
  checksum_sha256?: string | null;
  objectUrl?: string;
  bbox_local_m?: [number, number, number, number, number, number];
  encoding?: string | null;
  has_rgb?: boolean | null;
  layer?: WarehouseLiveVoxelChunk["layer"];
  source?: WarehouseLiveVoxelChunk["source"];
  point_count?: number | null;
};

export type LiveMapChunkCacheResult = {
  cachedChunks: CachedLiveMapChunk[];
  downloadedChunkIds: ReadonlySet<string>;
  inFlightChunkIds: ReadonlySet<string>;
  candidateChunkCount: number;
  droppedChunkCount: number;
  maxConcurrentDownloads: number;
};

function normalizeKind(value: unknown): CachedLiveMapChunkKind {
  if (
    value === "mesh" ||
    value === "point_cloud" ||
    value === "occupancy" ||
    value === "esdf" ||
    value === "costmap"
  ) {
    return value;
  }
  return "point_cloud";
}

function toBbox(
  value: WarehouseLiveVoxelChunk["bbox_local_m"],
): [number, number, number, number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 6) return undefined;
  const parsed = value.map(Number);
  if (parsed.some((item) => !Number.isFinite(item))) return undefined;
  return parsed as [number, number, number, number, number, number];
}

function shouldCreateObjectUrl(kind: CachedLiveMapChunkKind): boolean {
  return kind === "mesh";
}

export { chunkCacheKey } from "../utils/liveMapChunkRetention";

function chunkVersion(chunk: WarehouseLiveVoxelChunk): string {
  return [
    chunk.url ?? "",
    chunk.checksum_sha256 ?? "",
    chunk.byte_size ?? "",
  ].join("|");
}

function shouldBatchChunkDownloads(
  mode: LiveMapChunkCacheMode,
  pendingCount: number,
): boolean {
  void pendingCount;
  return mode === "replay";
}

function fetchChunkOnce(
  key: string,
  url: string,
  token: string | null | undefined,
  signal: AbortSignal,
  flightId?: string | null,
  chunkId?: string | null,
): Promise<ArrayBuffer> {
  const existing = inFlightChunkFetches.get(key);
  if (existing) return existing;
  // Coalesce concurrent fetches into one batched request when we know the
  // flight + chunk id; otherwise fall back to the single-chunk endpoint.
  const request = (
    flightId && chunkId
      ? fetchWarehouseLiveChunkBatched(flightId, chunkId, key, url, token, signal)
      : fetchWarehouseLiveChunk(url, token, signal, key)
  ).finally(() => {
    inFlightChunkFetches.delete(key);
  });
  inFlightChunkFetches.set(key, request);
  return request;
}

function selectDownloadableChunks(
  chunks: WarehouseLiveVoxelChunk[],
  mode: LiveMapChunkCacheMode,
): WarehouseLiveVoxelChunk[] {
  return selectDownloadableChunksPerLayer(chunks, mode, {
    maxBytesPerChunk: LIVE_MAX_CACHED_BYTES,
    maxReplayBytes: REPLAY_MAX_CACHED_BYTES,
    maxReplayChunks: REPLAY_MAX_CACHED_CHUNKS,
  });
}

async function runWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  if (items.length === 0) return;

  let index = 0;
  const runners = Array.from(
    { length: Math.min(limit, items.length) },
    async () => {
      while (index < items.length) {
        const current = items[index];
        index += 1;
        await worker(current);
      }
    },
  );
  await Promise.all(runners);
}

function resetCacheState(
  entriesRef: MutableRefObject<Map<string, CachedLiveMapChunk>>,
  setEntries: Dispatch<SetStateAction<Map<string, CachedLiveMapChunk>>>,
  setDownloadedChunkIds: Dispatch<SetStateAction<Set<string>>>,
  setInFlightChunkIds: Dispatch<SetStateAction<Set<string>>>,
  downloadedRef: MutableRefObject<Set<string>>,
  inFlightRef: MutableRefObject<Set<string>>,
) {
  for (const entry of entriesRef.current.values()) {
    if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
  }
  entriesRef.current = new Map();
  downloadedRef.current = new Set();
  inFlightRef.current = new Set();
  setEntries(new Map());
  setDownloadedChunkIds(new Set());
  setInFlightChunkIds(new Set());
}

export function useLiveMapChunkCache(
  flightId: string | null | undefined,
  chunks: WarehouseLiveVoxelChunk[],
  token?: string | null,
  options: {
    mode?: LiveMapChunkCacheMode;
    visibleLayers?: LiveVoxelLayers;
    config?: LiveMapRuntimeConfig;
  } = {},
): LiveMapChunkCacheResult {
  const mode = options.mode ?? "live";
  const config = options.config ?? DEFAULT_LIVE_MAP_CONFIG;
  const visibleLayers = options.visibleLayers;

  const [entries, setEntries] = useState(new Map<string, CachedLiveMapChunk>());
  const [downloadedChunkIds, setDownloadedChunkIds] = useState<Set<string>>(
    new Set(),
  );
  const [inFlightChunkIds, setInFlightChunkIds] = useState<Set<string>>(
    new Set(),
  );

  const entriesRef = useRef(entries);
  const downloadedRef = useRef(downloadedChunkIds);
  const inFlightRef = useRef(inFlightChunkIds);
  const abortControllersRef = useRef(new Map<string, AbortController>());
  const previousFlightIdRef = useRef<string | null>(null);
  const downloadEffectGenRef = useRef(0);
  const frameBatchRef = useRef<ChunkCacheFrameBatch>(emptyFrameBatch());
  const frameFlushRef = useRef<number | null>(null);

  const flushFrameBatch = useCallback(() => {
    frameFlushRef.current = null;
    const batch = frameBatchRef.current;
    frameBatchRef.current = emptyFrameBatch();

    if (batch.entries.size > 0) {
      const next = new Map(entriesRef.current);
      for (const [key, entry] of batch.entries) {
        const previous = next.get(key);
        if (previous?.objectUrl && previous.objectUrl !== entry.objectUrl) {
          URL.revokeObjectURL(previous.objectUrl);
        }
        next.set(key, entry);
      }
      entriesRef.current = next;
      setEntries(next);
    }

    if (batch.downloadedKeys.size > 0) {
      const next = new Set(downloadedRef.current);
      for (const key of batch.downloadedKeys) next.add(key);
      downloadedRef.current = next;
      setDownloadedChunkIds(next);
    }

    if (batch.inFlightAdds.size > 0 || batch.inFlightRemoves.size > 0) {
      const next = new Set(inFlightRef.current);
      for (const key of batch.inFlightAdds) next.add(key);
      for (const key of batch.inFlightRemoves) next.delete(key);
      inFlightRef.current = next;
      setInFlightChunkIds(next);
    }
  }, []);

  const scheduleFrameFlush = useCallback(() => {
    if (frameFlushRef.current != null) return;
    frameFlushRef.current = window.requestAnimationFrame(flushFrameBatch);
  }, [flushFrameBatch]);

  const queueInFlightChange = useCallback(
    (key: string, inFlight: boolean) => {
      const batch = frameBatchRef.current;
      if (inFlight) {
        batch.inFlightRemoves.delete(key);
        batch.inFlightAdds.add(key);
      } else {
        batch.inFlightAdds.delete(key);
        batch.inFlightRemoves.add(key);
      }
      scheduleFrameFlush();
    },
    [scheduleFrameFlush],
  );

  const queueCompletedChunk = useCallback(
    (key: string, entry: CachedLiveMapChunk) => {
      frameBatchRef.current.entries.set(key, entry);
      frameBatchRef.current.downloadedKeys.add(key);
      scheduleFrameFlush();
    },
    [scheduleFrameFlush],
  );

  const discardFrameBatch = useCallback(() => {
    if (frameFlushRef.current != null) {
      window.cancelAnimationFrame(frameFlushRef.current);
      frameFlushRef.current = null;
    }
    for (const entry of frameBatchRef.current.entries.values()) {
      if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
    }
    frameBatchRef.current = emptyFrameBatch();
  }, []);

  const candidates = useMemo(() => {
    const withUrls = chunks.filter((chunk) => Boolean(chunk.url));
    const layerFiltered = visibleLayers
      ? filterChunksForDownload(withUrls, visibleLayers, config.preferred_layer)
      : withUrls;
    return selectDownloadableChunks(layerFiltered, mode);
  }, [chunks, config.preferred_layer, mode, visibleLayers]);
  const candidateChunkCount = useMemo(() => {
    const withUrls = chunks.filter((chunk) => Boolean(chunk.url));
    return visibleLayers
      ? filterChunksForDownload(withUrls, visibleLayers, config.preferred_layer).length
      : withUrls.length;
  }, [chunks, config.preferred_layer, visibleLayers]);

  const candidateByKey = useMemo(() => {
    if (!flightId) return new Map<string, WarehouseLiveVoxelChunk>();
    return new Map(
      candidates.map((chunk) => [chunkCacheKey(flightId, chunk), chunk]),
    );
  }, [candidates, flightId]);

  const pendingDownloads = useMemo(() => {
    if (!flightId) return [];
    return candidates.filter((chunk) => {
      const key = chunkCacheKey(flightId, chunk);
      const existing = entries.get(key);
      if (!existing) return true;
      if (existing.url !== chunk.url) return true;
      if (
        chunk.checksum_sha256 &&
        existing.checksum_sha256 !== chunk.checksum_sha256
      ) {
        return true;
      }
      if (
        chunk.byte_size != null &&
        existing.bytes !== chunk.byte_size &&
        !chunk.checksum_sha256
      ) {
        return true;
      }
      return false;
    });
  }, [candidates, entries, flightId]);

  const uniquePendingDownloads = useMemo(() => {
    if (!flightId) return [];
    const seen = new Set<string>();
    return pendingDownloads.filter((chunk) => {
      const key = chunkCacheKey(flightId, chunk);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [flightId, pendingDownloads]);

  const pendingSignature = useMemo(() => {
    if (!flightId) return "";
    return uniquePendingDownloads
      .map((chunk) => `${chunkCacheKey(flightId, chunk)}:${chunkVersion(chunk)}`)
      .sort()
      .join("|");
  }, [flightId, uniquePendingDownloads]);

  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  useEffect(() => {
    downloadedRef.current = downloadedChunkIds;
  }, [downloadedChunkIds]);

  useEffect(() => {
    inFlightRef.current = inFlightChunkIds;
  }, [inFlightChunkIds]);

  useEffect(() => {
    if (!flightId) {
      discardFrameBatch();
      if (previousFlightIdRef.current) {
        clearLiveMapChunkFetchCache(previousFlightIdRef.current);
      }
      for (const controller of abortControllersRef.current.values()) {
        controller.abort();
      }
      abortControllersRef.current.clear();
      resetCacheState(
        entriesRef,
        setEntries,
        setDownloadedChunkIds,
        setInFlightChunkIds,
        downloadedRef,
        inFlightRef,
      );
      previousFlightIdRef.current = null;
      return;
    }

    const previousFlightId = previousFlightIdRef.current;
    if (previousFlightId !== null && previousFlightId !== flightId) {
      discardFrameBatch();
      clearLiveMapChunkFetchCache(previousFlightId);
      for (const controller of abortControllersRef.current.values()) {
        controller.abort();
      }
      abortControllersRef.current.clear();
      resetCacheState(
        entriesRef,
        setEntries,
        setDownloadedChunkIds,
        setInFlightChunkIds,
        downloadedRef,
        inFlightRef,
      );
    }
    previousFlightIdRef.current = flightId;
  }, [discardFrameBatch, flightId]);

  useEffect(() => () => discardFrameBatch(), [discardFrameBatch]);

  useEffect(() => {
    liveMapDebugLog("chunks_scheduled_for_download", {
      flight_id: flightId,
      mode,
      count: uniquePendingDownloads.length,
      entries_cached: entries.size,
    });
  }, [entries.size, flightId, mode, uniquePendingDownloads.length]);

  useEffect(() => {
    if (!flightId || uniquePendingDownloads.length === 0) return;

    const useBatchDownloads = shouldBatchChunkDownloads(
      mode,
      uniquePendingDownloads.length,
    );
    const maxConcurrent = useBatchDownloads
      ? Math.min(uniquePendingDownloads.length, LIVE_MAP_BATCH_MAX_CHUNKS)
      : config.frontend.max_concurrent_chunk_downloads;
    const effectGen = ++downloadEffectGenRef.current;

    void runWithConcurrency(uniquePendingDownloads, maxConcurrent, async (chunk) => {
      if (!chunk.url || !flightId) return;
      if (downloadEffectGenRef.current !== effectGen) return;

      const key = chunkCacheKey(flightId, chunk);
      if (entriesRef.current.has(key)) {
        return;
      }

      const controller = new AbortController();
      abortControllersRef.current.set(key, controller);

      queueInFlightChange(key, true);

      try {
        // Replay always batches; live uses batch only for catch-up bursts (≥3 pending).
        const arrayBuffer = await fetchChunkOnce(
          key,
          chunk.url,
          token,
          controller.signal,
          useBatchDownloads ? flightId : null,
          useBatchDownloads ? chunk.id : null,
        );

        if (downloadEffectGenRef.current !== effectGen) {
          return;
        }
        if (controller.signal.aborted) {
          return;
        }
        if (arrayBuffer.byteLength === 0) {
          throw new Error("empty chunk body");
        }

        const latest = candidateByKey.get(key);
        if (!latest || latest.url !== chunk.url) return;

        const kind = normalizeKind(chunk.kind);
        const objectUrl = shouldCreateObjectUrl(kind)
          ? URL.createObjectURL(new Blob([arrayBuffer]))
          : undefined;

        const nextEntry: CachedLiveMapChunk = {
          cacheKey: key,
          id: chunk.id,
          kind,
          url: chunk.url,
          bytes: arrayBuffer.byteLength,
          loaded: true,
          arrayBuffer,
          checksum_sha256: chunk.checksum_sha256,
          objectUrl,
          bbox_local_m: toBbox(chunk.bbox_local_m),
          encoding: chunk.encoding,
          has_rgb: chunk.has_rgb,
          layer: chunk.layer,
          source: chunk.source,
          point_count: chunk.point_count,
        };

        queueCompletedChunk(key, nextEntry);
        liveMapDebugLog("chunk_downloaded", {
          flight_id: flightId,
          cache_key: key,
          bytes: arrayBuffer.byteLength,
        });
      } catch {
        /* retried when pendingSignature changes */
      } finally {
        abortControllersRef.current.delete(key);
        queueInFlightChange(key, false);
      }
    });

    return () => {
      // Invalidate stale workers without aborting in-flight fetches (StrictMode-safe).
      downloadEffectGenRef.current += 1;
    };
  }, [
    candidateByKey,
    config.frontend.max_concurrent_chunk_downloads,
    flightId,
    mode,
    pendingSignature,
    queueCompletedChunk,
    queueInFlightChange,
    token,
    uniquePendingDownloads,
    visibleLayers,
  ]);

  const cachedChunks = useMemo(() => {
    if (!flightId) return [];
    const seen = new Set<string>();
    const loaded: CachedLiveMapChunk[] = [];
    for (const chunk of chunks) {
      const key = chunkCacheKey(flightId, chunk);
      if (seen.has(key)) continue;
      const entry = entries.get(key);
      if (!entry) continue;
      seen.add(key);
      loaded.push(entry);
    }
    return loaded;
  }, [chunks, entries, flightId]);

  return {
    cachedChunks,
    downloadedChunkIds,
    inFlightChunkIds,
    candidateChunkCount,
    droppedChunkCount: Math.max(0, candidateChunkCount - candidates.length),
    maxConcurrentDownloads: config.frontend.max_concurrent_chunk_downloads,
  };
}
