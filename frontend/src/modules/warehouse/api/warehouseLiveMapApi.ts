import { getApiBaseUrl } from "../../../app/config/env";
import {
  httpRequest,
  resolveApiUrl,
  shouldAttachBearerToken,
} from "../../../shared/api/httpClient";

export type WarehouseLivePose = {
  x_m: number;
  y_m: number;
  z_m: number;
  yaw_deg?: number | null;
  frame_id: string;
};

export type WarehouseLiveVoxelChunk = {
  id: string;
  kind: "mesh" | "point_cloud" | "occupancy" | "esdf" | "costmap";
  url?: string | null;
  content_type?: string | null;
  asset_id?: number | null;
  block_ids?: string[];
  point_count?: number | null;
  byte_size?: number | null;
  checksum_sha256?: string | null;
  bbox_local_m?: number[] | null;
  preview_points_m?: number[][] | null;
  sequence: number;
  source?:
    | "mid360_raw"
    | "rgbd_colored"
    | "nvblox_color"
    | "nvblox_esdf"
    | "nvblox_tsdf"
    | "nvblox_mesh"
    | "odom"
    | null;
  layer?:
    | "mid360_lidar"
    | "rgbd_colored"
    | "nvblox_color"
    | "nvblox_esdf"
    | "nvblox_tsdf"
    | "nvblox_mesh"
    | null;
  has_rgb?: boolean | null;
  encoding?: string | null;
  layer_type?: string | null;
  frame_id?: string | null;
  stamp?: string | null;
  priority?: number | null;
};

export type WarehouseLiveMapManifestSummary = {
  map_quality?: string;
  rgbd_colored_available?: boolean;
  nvblox_available?: boolean;
  raw_lidar_only?: boolean;
  chunk_counts?: Record<string, number>;
  point_counts?: Record<string, number>;
  missing_topics?: string[];
};

export type NvbloxLiveStatus =
  | "off"
  | "warming"
  | "live"
  | "degraded"
  | "error";

export type WarehouseLiveHealthFlags = {
  coverage_percent?: number | null;
  drift_estimate_m?: number | null;
  stale_costmap: boolean;
  missing_mesh: boolean;
  missing_point_cloud: boolean;
  nvblox_ready: boolean;
  nvblox_status?: NvbloxLiveStatus | null;
  rgbd_live?: boolean | null;
  lidar_live?: boolean | null;
  mapping_recording: boolean;
  stack_running: boolean;
};

export type WarehouseLiveMapUpdate = {
  type: "live_map_update";
  flight_id: string;
  timestamp: string;
  frame_id: string;
  pose: WarehouseLivePose;
  changed_chunks: WarehouseLiveVoxelChunk[];
  removed_chunk_ids: string[];
  scan_path_sample: WarehouseLivePose[];
  health: WarehouseLiveHealthFlags;
  finalized_scan_job_id?: number | null;
};

export type WarehouseLiveMapSnapshot = {
  type: "live_map_snapshot";
  flight_id: string;
  status: "empty" | "live" | "stale" | "finalized";
  last_update_at?: string | null;
  updates: WarehouseLiveMapUpdate[];
  manifest?: WarehouseLiveMapManifestSummary | null;
};

export type WarehouseLiveMapFinalized = {
  type: "live_map_finalized";
  flight_id: string;
  finalized_scan_job_id: number;
  last_update_at?: string | null;
};

export type WarehouseLiveMapMessage =
  | WarehouseLiveMapUpdate
  | WarehouseLiveMapSnapshot
  | WarehouseLiveMapFinalized
  | { type: "pong" };

export function isWarehouseLiveMapUpdate(
  value: unknown,
): value is WarehouseLiveMapUpdate {
  if (!value || typeof value !== "object") return false;
  const update = value as Partial<WarehouseLiveMapUpdate>;
  return (
    update.type === "live_map_update" &&
    typeof update.flight_id === "string" &&
    typeof update.timestamp === "string" &&
    Array.isArray(update.changed_chunks) &&
    Array.isArray(update.removed_chunk_ids) &&
    Array.isArray(update.scan_path_sample)
  );
}

export function isWarehouseLiveMapSnapshot(
  value: unknown,
): value is WarehouseLiveMapSnapshot {
  if (!value || typeof value !== "object") return false;
  const snapshot = value as Partial<WarehouseLiveMapSnapshot>;
  return (
    snapshot.type === "live_map_snapshot" &&
    typeof snapshot.flight_id === "string" &&
    Array.isArray(snapshot.updates)
  );
}

function resolveWarehouseWebSocketBase(): string {
  const apiBase = getApiBaseUrl();
  if (!apiBase) {
    return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
  }
  if (apiBase.startsWith("http://") || apiBase.startsWith("https://")) {
    return apiBase.replace(/^http/, "ws");
  }
  if (apiBase.startsWith("/")) {
    return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${apiBase}`;
  }
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/${apiBase}`;
}

export function resolveWarehouseLiveMapWebSocketUrl(
  flightId: string,
  token?: string | null,
): string {
  const base = `${resolveWarehouseWebSocketBase()}/warehouse/live-map/${encodeURIComponent(flightId)}/stream`;
  const trimmed = token?.trim();
  if (!trimmed) return base;
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}token=${encodeURIComponent(trimmed)}`;
}

export function connectWarehouseLiveMap(
  flightId: string,
  handlers: {
    onMessage: (message: WarehouseLiveMapMessage) => void;
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (event: Event) => void;
  },
  token?: string | null,
): WebSocket {
  const socket = new WebSocket(resolveWarehouseLiveMapWebSocketUrl(flightId, token));
  socket.addEventListener("open", () => handlers.onOpen?.());
  socket.addEventListener("close", () => handlers.onClose?.());
  socket.addEventListener("error", (event) => handlers.onError?.(event));
  socket.addEventListener("message", (event) => {
    try {
      handlers.onMessage(
        JSON.parse(String(event.data)) as WarehouseLiveMapMessage,
      );
    } catch {
      handlers.onError?.(new Event("malformed-live-map-message"));
    }
  });
  return socket;
}

export function disconnectWarehouseLiveMap(socket: WebSocket | null): void {
  if (!socket) return;
  if (
    socket.readyState === WebSocket.OPEN ||
    socket.readyState === WebSocket.CONNECTING
  ) {
    socket.close();
  }
}

export async function fetchWarehouseLiveMapConfig(
  token?: string | null,
): Promise<{ live_map: LiveMapRuntimeConfig }> {
  return httpRequest<{ live_map: LiveMapRuntimeConfig }>(
    "/warehouse/live-map/config",
    { token, skipUnauthorizedRedirect: true },
  );
}

export type LiveMapRuntimeConfig = {
  raw_lidar: {
    enabled: boolean;
    max_hz: number;
    voxel_size: number;
    max_points: number;
  };
  frontend: {
    max_concurrent_chunk_downloads: number;
    max_points_per_layer: number;
  };
  preferred_layer: "rgbd_colored" | "nvblox_color" | "mid360_raw";
};

export async function fetchWarehouseLiveMapDiagnostics(
  token?: string | null,
): Promise<Record<string, unknown>> {
  return httpRequest<Record<string, unknown>>("/warehouse/live-map/diagnostics", {
    token,
    skipUnauthorizedRedirect: true,
  });
}

export async function fetchWarehouseLiveMapSnapshot(
  flightId: string,
  token?: string | null,
): Promise<WarehouseLiveMapSnapshot> {
  return httpRequest<WarehouseLiveMapSnapshot>(
    `/warehouse/live-map/${encodeURIComponent(flightId)}/snapshot`,
    { token, skipUnauthorizedRedirect: true },
  );
}

const chunkBinaryCache = new Map<string, ArrayBuffer>();
const chunkEtagByKey = new Map<string, string>();

export function getLiveMapChunkBinaryCache(
  cacheKey: string,
): ArrayBuffer | undefined {
  return chunkBinaryCache.get(cacheKey);
}

export function clearLiveMapChunkFetchCache(flightId?: string | null): void {
  if (!flightId) {
    chunkBinaryCache.clear();
    chunkEtagByKey.clear();
    return;
  }
  const prefix = `${flightId}:`;
  for (const key of chunkBinaryCache.keys()) {
    if (!key.startsWith(prefix)) continue;
    chunkBinaryCache.delete(key);
    chunkEtagByKey.delete(key);
  }
}

export async function fetchWarehouseLiveChunk(
  url: string,
  token?: string | null,
  signal?: AbortSignal,
  cacheKey?: string,
  useConditional = true,
): Promise<ArrayBuffer> {
  const headers = new Headers();
  const authToken = token?.trim();
  if (shouldAttachBearerToken(authToken)) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  const cachedBody =
    cacheKey && useConditional ? chunkBinaryCache.get(cacheKey) : undefined;
  const etag =
    cacheKey && cachedBody && useConditional
      ? chunkEtagByKey.get(cacheKey)
      : undefined;
  if (etag) {
    headers.set("If-None-Match", etag);
  }

  const response = await fetch(resolveApiUrl(url), {
    credentials: "include",
    headers,
    signal,
    cache: "no-store",
  });

  if (response.status === 304) {
    if (cachedBody) {
      return cachedBody;
    }
    if (cacheKey && useConditional) {
      return fetchWarehouseLiveChunk(url, token, signal, cacheKey, false);
    }
    throw new Error("Live chunk fetch returned 304 without a cached body");
  }

  if (!response.ok) {
    throw new Error(`Live chunk fetch failed: ${response.status}`);
  }

  const body = await response.arrayBuffer();
  if (body.byteLength === 0) {
    throw new Error("Live chunk fetch returned an empty body");
  }

  if (cacheKey) {
    chunkBinaryCache.set(cacheKey, body);
    const responseEtag = response.headers?.get?.("ETag") ?? null;
    if (responseEtag) {
      chunkEtagByKey.set(cacheKey, responseEtag);
    }
  }

  return body;
}

// ---------------------------------------------------------------------------
// Bulk chunk download (kills the per-chunk N+1 fan-out on snapshot/replay load)
// ---------------------------------------------------------------------------

const LIVE_MAP_BATCH_MAX_CHUNKS = 256;
const LIVE_MAP_BATCH_FLUSH_MS = 12;

type BatchFrame = { status: number; byteSize: number; data: ArrayBuffer | null };

/**
 * Parse the length-prefixed binary stream produced by the batch endpoint.
 * Layout, repeated per chunk:
 *   [uint32 big-endian header_len][header_len bytes UTF-8 JSON][byte_size data bytes]
 */
export function parseLiveMapChunkBatch(
  buffer: ArrayBuffer,
): Map<string, BatchFrame> {
  const out = new Map<string, BatchFrame>();
  const view = new DataView(buffer);
  const decoder = new TextDecoder();
  let offset = 0;
  const total = buffer.byteLength;
  while (offset + 4 <= total) {
    const headerLen = view.getUint32(offset, false);
    offset += 4;
    if (headerLen <= 0 || offset + headerLen > total) break;
    const headerBytes = new Uint8Array(buffer, offset, headerLen);
    offset += headerLen;
    let header: {
      chunk_id?: string;
      status?: number;
      byte_size?: number;
    };
    try {
      header = JSON.parse(decoder.decode(headerBytes));
    } catch {
      break;
    }
    const chunkId = String(header.chunk_id ?? "");
    const status = Number(header.status ?? 0);
    const byteSize = Number(header.byte_size ?? 0);
    let data: ArrayBuffer | null = null;
    if (status === 200 && byteSize > 0) {
      if (offset + byteSize > total) break;
      data = buffer.slice(offset, offset + byteSize);
      offset += byteSize;
    }
    if (chunkId) out.set(chunkId, { status, byteSize, data });
  }
  return out;
}

type BatchWaiter = {
  chunkId: string;
  cacheKey: string;
  url: string;
  token?: string | null;
  signal?: AbortSignal;
  resolve: (buffer: ArrayBuffer) => void;
  reject: (error: unknown) => void;
};

const batchQueues = new Map<string, BatchWaiter[]>();
const batchTimers = new Map<string, ReturnType<typeof setTimeout>>();

function rejectAborted(waiter: BatchWaiter): boolean {
  if (waiter.signal?.aborted) {
    waiter.reject(new DOMException("Aborted", "AbortError"));
    return true;
  }
  return false;
}

function fallbackToPerChunk(waiter: BatchWaiter): void {
  fetchWarehouseLiveChunk(waiter.url, waiter.token, waiter.signal, waiter.cacheKey)
    .then(waiter.resolve)
    .catch(waiter.reject);
}

async function runLiveMapChunkBatch(
  flightId: string,
  waiters: BatchWaiter[],
): Promise<void> {
  const ids = Array.from(new Set(waiters.map((w) => w.chunkId)));
  const headers = new Headers({ "Content-Type": "application/json" });
  const authToken = waiters.find((w) => w.token)?.token?.trim();
  if (shouldAttachBearerToken(authToken)) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  try {
    const response = await fetch(
      resolveApiUrl(
        `/warehouse/live-map/${encodeURIComponent(flightId)}/chunks/batch`,
      ),
      {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({ chunk_ids: ids }),
        cache: "no-store",
      },
    );
    if (!response.ok) {
      throw new Error(`Live chunk batch failed: ${response.status}`);
    }
    const frames = parseLiveMapChunkBatch(await response.arrayBuffer());
    for (const waiter of waiters) {
      if (rejectAborted(waiter)) continue;
      const frame = frames.get(waiter.chunkId);
      if (frame?.data && frame.data.byteLength > 0) {
        chunkBinaryCache.set(waiter.cacheKey, frame.data);
        waiter.resolve(frame.data);
      } else {
        // Missing from the batch (e.g. produced after the request) → per-chunk.
        fallbackToPerChunk(waiter);
      }
    }
  } catch {
    // Whole batch failed → degrade gracefully to individual requests.
    for (const waiter of waiters) {
      if (rejectAborted(waiter)) continue;
      fallbackToPerChunk(waiter);
    }
  }
}

function flushLiveMapChunkBatch(flightId: string): void {
  const timer = batchTimers.get(flightId);
  if (timer) clearTimeout(timer);
  batchTimers.delete(flightId);
  const queued = batchQueues.get(flightId);
  batchQueues.delete(flightId);
  if (!queued || queued.length === 0) return;
  for (let i = 0; i < queued.length; i += LIVE_MAP_BATCH_MAX_CHUNKS) {
    void runLiveMapChunkBatch(
      flightId,
      queued.slice(i, i + LIVE_MAP_BATCH_MAX_CHUNKS),
    );
  }
}

/**
 * Coalesce many concurrent chunk fetches for a flight into a single batched
 * HTTP request. Serves from the in-memory cache when possible and falls back to
 * the per-chunk endpoint on any batch error, so behaviour is never worse than
 * the original N+1 path.
 */
export function fetchWarehouseLiveChunkBatched(
  flightId: string,
  chunkId: string,
  cacheKey: string,
  url: string,
  token?: string | null,
  signal?: AbortSignal,
): Promise<ArrayBuffer> {
  const cached = chunkBinaryCache.get(cacheKey);
  if (cached) return Promise.resolve(cached);
  if (!flightId || !chunkId) {
    return fetchWarehouseLiveChunk(url, token, signal, cacheKey);
  }
  return new Promise<ArrayBuffer>((resolve, reject) => {
    const waiter: BatchWaiter = {
      chunkId,
      cacheKey,
      url,
      token,
      signal,
      resolve,
      reject,
    };
    const queue = batchQueues.get(flightId) ?? [];
    queue.push(waiter);
    batchQueues.set(flightId, queue);
    if (queue.length >= LIVE_MAP_BATCH_MAX_CHUNKS) {
      flushLiveMapChunkBatch(flightId);
    } else if (!batchTimers.has(flightId)) {
      batchTimers.set(
        flightId,
        setTimeout(() => flushLiveMapChunkBatch(flightId), LIVE_MAP_BATCH_FLUSH_MS),
      );
    }
  });
}
