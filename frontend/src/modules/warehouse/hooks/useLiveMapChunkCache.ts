import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchWarehouseLiveChunk,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

const LIVE_MAX_CACHED_BYTES = 48 * 1024 * 1024;
const LIVE_MAX_CACHED_CHUNKS = 48;
const REPLAY_MAX_CACHED_BYTES = 256 * 1024 * 1024;
const REPLAY_MAX_CACHED_CHUNKS = 512;

export type LiveMapChunkCacheMode = "live" | "replay";

export type CachedLiveMapChunkKind =
    | "mesh"
    | "point_cloud"
    | "occupancy"
    | "esdf"
    | "costmap";

export type CachedLiveMapChunk = {
  id: string;
  kind: CachedLiveMapChunkKind;
  url: string;
  bytes: number;
  loaded: boolean;
  arrayBuffer: ArrayBuffer;
  objectUrl?: string;
  bbox_local_m?: [number, number, number, number, number, number];
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

function selectDownloadableChunks(
    chunks: WarehouseLiveVoxelChunk[],
    mode: LiveMapChunkCacheMode,
): WarehouseLiveVoxelChunk[] {
  const sorted = [...chunks]
      .filter(
          (chunk) =>
              Boolean(chunk.url) &&
              (chunk.byte_size ?? 0) > 0,
      )
      .sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0));

  if (mode === "live") {
    return sorted
        .filter((chunk) => (chunk.byte_size ?? 0) <= LIVE_MAX_CACHED_BYTES)
        .slice(-LIVE_MAX_CACHED_CHUNKS);
  }

  let totalBytes = 0;
  const selected: WarehouseLiveVoxelChunk[] = [];
  for (const chunk of sorted) {
    const bytes = chunk.byte_size ?? 0;
    if (bytes > LIVE_MAX_CACHED_BYTES) continue;
    if (selected.length >= REPLAY_MAX_CACHED_CHUNKS) break;
    if (totalBytes + bytes > REPLAY_MAX_CACHED_BYTES) break;
    selected.push(chunk);
    totalBytes += bytes;
  }
  return selected;
}

export function useLiveMapChunkCache(
    chunks: WarehouseLiveVoxelChunk[],
    token?: string | null,
    options: { mode?: LiveMapChunkCacheMode } = {},
): CachedLiveMapChunk[] {
  const mode = options.mode ?? "live";
  const [entries, setEntries] = useState(new Map<string, CachedLiveMapChunk>());
  const entriesRef = useRef(entries);

  const candidates = useMemo(
      () => selectDownloadableChunks(chunks, mode),
      [chunks, mode],
  );

  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  useEffect(() => {
    const controller = new AbortController();

    void Promise.allSettled(
        candidates.map(async (chunk) => {
          if (!chunk.url) return;

          const existing = entriesRef.current.get(chunk.id);
          if (
              existing &&
              existing.url === chunk.url &&
              existing.bytes === chunk.byte_size
          ) {
            return;
          }

          const arrayBuffer = await fetchWarehouseLiveChunk(
              chunk.url,
              token,
              controller.signal,
          );

          if (controller.signal.aborted) return;

          const kind = normalizeKind(chunk.kind);
          const objectUrl = shouldCreateObjectUrl(kind)
              ? URL.createObjectURL(new Blob([arrayBuffer]))
              : undefined;

          const nextEntry: CachedLiveMapChunk = {
            id: chunk.id,
            kind,
            url: chunk.url,
            bytes: arrayBuffer.byteLength,
            loaded: true,
            arrayBuffer,
            objectUrl,
            bbox_local_m: toBbox(chunk.bbox_local_m),
          };

          setEntries((current) => {
            const previous = current.get(chunk.id);
            if (previous?.objectUrl && previous.objectUrl !== objectUrl) {
              URL.revokeObjectURL(previous.objectUrl);
            }

            const next = new Map(current);
            next.set(chunk.id, nextEntry);

            const candidateIds = new Set(candidates.map((item) => item.id));
            for (const [id, entry] of next) {
              if (!candidateIds.has(id)) {
                if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
                next.delete(id);
              }
            }

            return next;
          });
        }),
    );

    return () => {
      controller.abort();
    };
  }, [candidates, token]);

  useEffect(() => {
    return () => {
      for (const entry of entriesRef.current.values()) {
        if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
      }
    };
  }, []);

  return Array.from(entries.values());
}
