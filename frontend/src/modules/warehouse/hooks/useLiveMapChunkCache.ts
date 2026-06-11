import {
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
  clearLiveMapChunkFetchCache,
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
  layer?: string | null;
  source?: string | null;
  point_count?: number | null;
};

export type LiveMapChunkCacheResult = {
  cachedChunks: CachedLiveMapChunk[];
  downloadedChunkIds: ReadonlySet<string>;
  inFlightChunkIds: ReadonlySet<string>;
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

function fetchChunkOnce(
  key: string,
  url: string,
  token: string | null | undefined,
  signal: AbortSignal,
): Promise<ArrayBuffer> {
  const existing = inFlightChunkFetches.get(key);
  if (existing) return existing;
  const request = fetchWarehouseLiveChunk(url, token, signal, key).finally(() => {
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

  const candidates = useMemo(() => {
    const withUrls = chunks.filter((chunk) => Boolean(chunk.url));
    const layerFiltered =
      mode === "replay" || !visibleLayers
        ? withUrls
        : filterChunksForDownload(
            withUrls,
            visibleLayers,
            config.preferred_layer,
          );
    return selectDownloadableChunks(layerFiltered, mode);
  }, [chunks, config.preferred_layer, mode, visibleLayers]);

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
  }, [flightId]);

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

    const maxConcurrent = config.frontend.max_concurrent_chunk_downloads;
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

      setInFlightChunkIds((current) => {
        const next = new Set(current);
        next.add(key);
        inFlightRef.current = next;
        return next;
      });

      try {
        const arrayBuffer = await fetchChunkOnce(
          key,
          chunk.url,
          token,
          controller.signal,
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

        setEntries((current) => {
          const previous = current.get(key);
          if (previous?.objectUrl && previous.objectUrl !== objectUrl) {
            URL.revokeObjectURL(previous.objectUrl);
          }
          const next = new Map(current);
          next.set(key, nextEntry);
          entriesRef.current = next;
          return next;
        });

        setDownloadedChunkIds((current) => {
          const next = new Set(current);
          next.add(key);
          downloadedRef.current = next;
          return next;
        });
        liveMapDebugLog("chunk_downloaded", {
          flight_id: flightId,
          cache_key: key,
          bytes: arrayBuffer.byteLength,
        });
      } catch {
        /* retried when pendingSignature changes */
      } finally {
        abortControllersRef.current.delete(key);
        setInFlightChunkIds((current) => {
          const next = new Set(current);
          next.delete(key);
          inFlightRef.current = next;
          return next;
        });
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
    pendingSignature,
    token,
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
  };
}
