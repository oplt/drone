import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearLiveMapChunkFetchCache,
  fetchWarehouseLiveChunk,
  fetchWarehouseLiveChunkBatched,
  getLiveMapChunkBinaryCache,
  isWarehouseLiveMapSnapshot,
  isWarehouseLiveMapUpdate,
  type WarehouseLiveMapSnapshot,
} from "../api/warehouseLiveMapApi";
import {
  applyWarehouseLiveMapMessage,
  mergeUpdate,
} from "../hooks/useWarehouseLiveVoxelMap";

describe("warehouse live map API", () => {
  it("parses live update DTOs", () => {
    const update = {
      type: "live_map_update",
      flight_id: "flight-1",
      timestamp: "2026-06-01T12:00:00Z",
      frame_id: "odom",
      pose: { x_m: 1, y_m: 2, z_m: 1, frame_id: "odom" },
      changed_chunks: [{ id: "chunk-1", kind: "mesh", sequence: 1 }],
      removed_chunk_ids: [],
      scan_path_sample: [],
      health: {
        stale_costmap: false,
        missing_mesh: false,
        missing_point_cloud: true,
        nvblox_ready: true,
        mapping_recording: true,
        stack_running: true,
      },
    };

    expect(isWarehouseLiveMapUpdate(update)).toBe(true);
  });

  it("applies snapshots and removes stale chunks", () => {
    const snapshot: WarehouseLiveMapSnapshot = {
      type: "live_map_snapshot",
      flight_id: "flight-1",
      status: "live",
      updates: [
        {
          type: "live_map_update",
          flight_id: "flight-1",
          timestamp: "2026-06-01T12:00:00Z",
          frame_id: "odom",
          pose: { x_m: 0, y_m: 0, z_m: 0, frame_id: "odom" },
          changed_chunks: [{ id: "a", kind: "mesh", sequence: 1 }],
          removed_chunk_ids: [],
          scan_path_sample: [],
          health: {
            stale_costmap: false,
            missing_mesh: false,
            missing_point_cloud: true,
            nvblox_ready: true,
            mapping_recording: true,
            stack_running: true,
          },
        },
        {
          type: "live_map_update",
          flight_id: "flight-1",
          timestamp: "2026-06-01T12:00:01Z",
          frame_id: "odom",
          pose: { x_m: 1, y_m: 0, z_m: 0, frame_id: "odom" },
          changed_chunks: [{ id: "b", kind: "point_cloud", sequence: 2 }],
          removed_chunk_ids: ["a"],
          scan_path_sample: [{ x_m: 1, y_m: 0, z_m: 0, frame_id: "odom" }],
          health: {
            stale_costmap: false,
            missing_mesh: true,
            missing_point_cloud: false,
            nvblox_ready: true,
            mapping_recording: true,
            stack_running: true,
          },
        },
      ],
    };

    expect(isWarehouseLiveMapSnapshot(snapshot)).toBe(true);
    const result = applyWarehouseLiveMapMessage(
      { chunksById: new Map(), scanPath: [] },
      snapshot,
    );

    expect(Array.from(result.chunksById.keys())).toEqual(["b"]);
    expect(result.scanPath).toHaveLength(1);
  });

  it("mergeUpdate keeps canonical chunks instead of replacing them", () => {
    const base = { chunksById: new Map(), scanPath: [] as const };
    const first = mergeUpdate(base, {
      type: "live_map_update",
      flight_id: "flight-1",
      timestamp: "2026-06-01T12:00:00Z",
      frame_id: "odom",
      pose: { x_m: 0, y_m: 0, z_m: 0, frame_id: "odom" },
      changed_chunks: Array.from({ length: 3 }, (_, index) => ({
        id: `rgbd_${String(index + 1).padStart(6, "0")}`,
        kind: "point_cloud" as const,
        sequence: index + 1,
      })),
      removed_chunk_ids: [],
      scan_path_sample: [],
      health: {
        stale_costmap: false,
        missing_mesh: true,
        missing_point_cloud: false,
        nvblox_ready: true,
        mapping_recording: true,
        stack_running: true,
      },
    });

    const second = mergeUpdate(first, {
      type: "live_map_update",
      flight_id: "flight-1",
      timestamp: "2026-06-01T12:00:01Z",
      frame_id: "odom",
      pose: { x_m: 1, y_m: 0, z_m: 0, frame_id: "odom" },
      changed_chunks: [
        { id: "rgbd_000004", kind: "point_cloud", sequence: 4 },
      ],
      removed_chunk_ids: [],
      scan_path_sample: [],
      health: {
        stale_costmap: false,
        missing_mesh: true,
        missing_point_cloud: false,
        nvblox_ready: true,
        mapping_recording: true,
        stack_running: true,
      },
    });

    expect(first.chunksById.size).toBe(3);
    expect(second.chunksById.size).toBe(4);
    expect(second.chunksById.has("rgbd_000001")).toBe(true);
  });
});

afterEach(() => {
  clearLiveMapChunkFetchCache();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("fetchWarehouseLiveChunk", () => {
  it("stores and returns binary bodies for 200 responses", async () => {
    const body = new Uint8Array([9, 8, 7]).buffer;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(body, {
          status: 200,
          headers: { ETag: '"etag-200"' },
        }),
      ),
    );

    const loaded = await fetchWarehouseLiveChunk(
      "/warehouse/live-map/flight/chunks/rgbd_000001/download",
      null,
      undefined,
      "flight:rgbd_000001",
    );

    expect(loaded.byteLength).toBe(3);
    expect(getLiveMapChunkBinaryCache("flight:rgbd_000001")).toBe(loaded);
  });

  it("returns cached binary on 304 without reading an empty body", async () => {
    const body = new Uint8Array([1, 2, 3]).buffer;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(body, {
          status: 200,
          headers: { ETag: '"etag-abc"' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(null, {
          status: 304,
          headers: { ETag: '"etag-abc"' },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const cacheKey = "flight:rgbd_000001";
    const first = await fetchWarehouseLiveChunk(
      "/warehouse/live-map/flight/chunks/rgbd_000001/download",
      null,
      undefined,
      cacheKey,
    );
    const second = await fetchWarehouseLiveChunk(
      "/warehouse/live-map/flight/chunks/rgbd_000001/download",
      null,
      undefined,
      cacheKey,
    );

    expect(first.byteLength).toBe(3);
    expect(second).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1]?.headers?.get("If-None-Match")).toBe(
      '"etag-abc"',
    );
  });

  it("retries without conditional headers when 304 has no cached binary", async () => {
    const body = new Uint8Array([4, 5, 6]).buffer;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 304,
          headers: { ETag: '"etag-miss"' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(body, {
          status: 200,
          headers: { ETag: '"etag-miss"' },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const loaded = await fetchWarehouseLiveChunk(
      "/warehouse/live-map/flight/chunks/rgbd_000002/download",
      null,
      undefined,
      "flight:rgbd_000002",
    );

    expect(loaded.byteLength).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1]?.headers?.get("If-None-Match")).toBeNull();
    expect(fetchMock.mock.calls[1][1]?.headers?.get("If-None-Match")).toBeNull();
  });
});

describe("fetchWarehouseLiveChunkBatched", () => {
  it("posts JSON chunk_ids to the batch endpoint", async () => {
    vi.useFakeTimers();
    const body = new Uint8Array([1, 2, 3, 4]).buffer;
    const header = new TextEncoder().encode(
      JSON.stringify({
        chunk_id: "rgbd_000001",
        status: 200,
        byte_size: body.byteLength,
        content_type: "application/octet-stream",
        checksum_sha256: "abc",
      }),
    );
    const frame = new Uint8Array(4 + header.byteLength + body.byteLength);
    const view = new DataView(frame.buffer);
    view.setUint32(0, header.byteLength, false);
    frame.set(header, 4);
    frame.set(new Uint8Array(body), 4 + header.byteLength);

    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.method).toBe("POST");
      const headers = new Headers(init?.headers);
      expect(headers.get("Content-Type")).toBe("application/json");
      expect(JSON.parse(String(init?.body))).toEqual({
        chunk_ids: ["rgbd_000001"],
      });
      return new Response(frame.buffer, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const loadedPromise = fetchWarehouseLiveChunkBatched(
      "flight-1",
      "rgbd_000001",
      "flight-1:rgbd_000001",
      "/warehouse/live-map/flight-1/chunks/rgbd_000001/download",
      null,
    );
    await vi.advanceTimersByTimeAsync(20);
    const loaded = await loadedPromise;

    expect(loaded.byteLength).toBe(body.byteLength);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
