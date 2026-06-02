import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchWarehouseLiveChunk,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";

const MAX_CACHED_BYTES = 48 * 1024 * 1024;

export type LiveChunkCacheEntry = {
  id: string;
  bytes: number;
  loaded: boolean;
};

export function useLiveMapChunkCache(
  chunks: WarehouseLiveVoxelChunk[],
  token?: string | null,
): LiveChunkCacheEntry[] {
  const [entries, setEntries] = useState(
    new Map<string, LiveChunkCacheEntry>(),
  );
  const entriesRef = useRef(entries);
  const candidates = useMemo(
    () =>
      chunks
        .filter(
          (chunk) => chunk.url && (chunk.byte_size ?? 0) <= MAX_CACHED_BYTES,
        )
        .slice(-48),
    [chunks],
  );

  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  useEffect(() => {
    const controller = new AbortController();
    const next = new Map(entriesRef.current);

    void Promise.allSettled(
      candidates.map(async (chunk) => {
        if (!chunk.url || next.has(chunk.id)) return;
        const buffer = await fetchWarehouseLiveChunk(
          chunk.url,
          token,
          controller.signal,
        );
        next.set(chunk.id, {
          id: chunk.id,
          bytes: buffer.byteLength,
          loaded: true,
        });
      }),
    ).then(() => {
      if (!controller.signal.aborted) {
        const kept = new Map<string, LiveChunkCacheEntry>();
        for (const chunk of candidates) {
          const entry = next.get(chunk.id);
          if (entry) kept.set(chunk.id, entry);
        }
        setEntries(kept);
      }
    });

    return () => controller.abort();
  }, [candidates, token]);

  return Array.from(entries.values());
}
