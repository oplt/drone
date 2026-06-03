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
  sequence: number;
};

export type WarehouseLiveHealthFlags = {
  coverage_percent?: number | null;
  drift_estimate_m?: number | null;
  stale_costmap: boolean;
  missing_mesh: boolean;
  missing_point_cloud: boolean;
  nvblox_ready: boolean;
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

export async function fetchWarehouseLiveMapSnapshot(
  flightId: string,
  token?: string | null,
): Promise<WarehouseLiveMapSnapshot> {
  return httpRequest<WarehouseLiveMapSnapshot>(
    `/warehouse/live-map/${encodeURIComponent(flightId)}/snapshot`,
    { token, skipUnauthorizedRedirect: true },
  );
}

export async function fetchWarehouseLiveChunk(
  url: string,
  token?: string | null,
  signal?: AbortSignal,
): Promise<ArrayBuffer> {
  const headers = new Headers();
  const authToken = token?.trim();
  if (shouldAttachBearerToken(authToken)) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  const response = await fetch(resolveApiUrl(url), {
    credentials: "include",
    headers,
    signal,
  });
  if (!response.ok) {
    throw new Error(`Live chunk fetch failed: ${response.status}`);
  }
  return response.arrayBuffer();
}
