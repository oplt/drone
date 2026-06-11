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
