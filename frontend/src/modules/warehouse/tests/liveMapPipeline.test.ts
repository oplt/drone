import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  chunkCacheKey,
  useLiveMapChunkCache,
} from "../hooks/useLiveMapChunkCache";
import {
  applyWarehouseLiveMapMessage,
  mergeUpdate,
  warehouseLiveMapReconnectDelayMs,
  warehouseLiveMapSnapshotPollDelayMs,
} from "../hooks/useWarehouseLiveVoxelMap";
import { selectDownloadableChunksPerLayer } from "../utils/liveMapChunkRetention";
import {
  clearLiveMapChunkFetchCache,
  type WarehouseLiveVoxelChunk,
} from "../api/warehouseLiveMapApi";
import { filterChunksForDownload } from "../config/liveMapConfig";
import { DEFAULT_LAYER_VISIBILITY } from "../utils/liveMapLayerUtils";
import {
  defaultLayerVisibilityForChunks,
  hasColoredMapLayers,
  inferLayerKey,
  chunksAvailableByLayer,
  layerHasStoredChunks,
} from "../utils/liveMapLayerUtils";

describe("warehouseLiveMapReconnectDelayMs", () => {
  it("backs off exponentially and caps at 30 seconds", () => {
    const noDownwardJitter = () => 1;

    expect(warehouseLiveMapReconnectDelayMs(1, noDownwardJitter)).toBe(1_500);
    expect(warehouseLiveMapReconnectDelayMs(2, noDownwardJitter)).toBe(3_000);
    expect(warehouseLiveMapReconnectDelayMs(5, noDownwardJitter)).toBe(24_000);
    expect(warehouseLiveMapReconnectDelayMs(6, noDownwardJitter)).toBe(30_000);
    expect(warehouseLiveMapReconnectDelayMs(20, noDownwardJitter)).toBe(30_000);
  });

  it("applies bounded downward jitter", () => {
    expect(warehouseLiveMapReconnectDelayMs(2, () => 0)).toBe(2_400);
    expect(warehouseLiveMapReconnectDelayMs(2, () => 1)).toBe(3_000);
  });
});

describe("warehouseLiveMapSnapshotPollDelayMs", () => {
  it("uses capped exponential backoff for HTTP fallback polling", () => {
    const noDownwardJitter = () => 1;

    expect(warehouseLiveMapSnapshotPollDelayMs(1, noDownwardJitter)).toBe(1_500);
    expect(warehouseLiveMapSnapshotPollDelayMs(4, noDownwardJitter)).toBe(12_000);
    expect(warehouseLiveMapSnapshotPollDelayMs(6, noDownwardJitter)).toBe(30_000);
  });
});

describe("chunkCacheKey", () => {
  it("keys cache entries by flight and chunk id", () => {
    const rgbd: WarehouseLiveVoxelChunk = {
      id: "rgbd_000001",
      kind: "point_cloud",
      sequence: 1,
      source: "rgbd_colored",
      layer: "rgbd_colored",
    };
    const mid360: WarehouseLiveVoxelChunk = {
      id: "mid360_000001",
      kind: "point_cloud",
      sequence: 1,
      source: "mid360_raw",
      layer: "mid360_lidar",
    };

    expect(chunkCacheKey("flight_a", rgbd)).toBe(
      "flight_a:rgbd_colored:rgbd_000001",
    );
    expect(chunkCacheKey("flight_a", mid360)).toBe(
      "flight_a:mid360_raw:mid360_000001",
    );
    expect(chunkCacheKey("flight_a", rgbd)).not.toBe(
      chunkCacheKey("flight_a", mid360),
    );
  });
});

afterEach(() => {
  clearLiveMapChunkFetchCache();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("useLiveMapChunkCache", () => {
  it("does not re-download an already cached chunk across repeated snapshots", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const first: WarehouseLiveVoxelChunk[] = [
      {
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        url: "/warehouse/live-map/flight/chunks/rgbd_000001/download",
        byte_size: 3,
      },
    ];
    const second = first.map((chunk) => ({ ...chunk }));

    const { result, rerender } = renderHook(
      ({ chunks }) => useLiveMapChunkCache("flight", chunks),
      { initialProps: { chunks: first } },
    );

    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(1));
    rerender({ chunks: second });

    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("clears cached chunks when switching flights with reused chunk ids", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(new Uint8Array([1, 1, 1]), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(new Uint8Array([2, 2, 2]), {
          status: 200,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const chunkFor = (flight: string): WarehouseLiveVoxelChunk => ({
      id: "rgbd_000001",
      kind: "point_cloud",
      sequence: 1,
      source: "rgbd_colored",
      layer: "rgbd_colored",
      url: `/warehouse/live-map/${flight}/chunks/rgbd_000001/download`,
      byte_size: 3,
    });

    const { result, rerender } = renderHook(
      ({ flightId, chunks }) => useLiveMapChunkCache(flightId, chunks),
      {
        initialProps: {
          flightId: "flight_a",
          chunks: [chunkFor("flight_a")],
        },
      },
    );

    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(1));
    expect(result.current.cachedChunks[0].url).toContain("flight_a");

    rerender({
      flightId: "flight_b",
      chunks: [chunkFor("flight_b")],
    });

    await waitFor(() => expect(result.current.cachedChunks[0]?.url).toContain("flight_b"));
    expect(result.current.cachedChunks).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("deduplicates duplicate in-flight chunk requests", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const duplicateChunks: WarehouseLiveVoxelChunk[] = [
      {
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        url: "/warehouse/live-map/flight/chunks/rgbd_000001/download",
        byte_size: 3,
      },
      {
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        url: "/warehouse/live-map/flight/chunks/rgbd_000001/download",
        byte_size: 3,
      },
    ];

    const { result } = renderHook(() =>
      useLiveMapChunkCache("flight", duplicateChunks),
    );

    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("batches same-frame replay completions into one animation-frame flush", async () => {
    const frameCallbacks: FrameRequestCallback[] = [];
    const requestFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        frameCallbacks.push(callback);
        return frameCallbacks.length;
      });
    const fetchMock = vi.fn(async () =>
      new Response(new Uint8Array([1, 2, 3]), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const chunks: WarehouseLiveVoxelChunk[] = Array.from(
      { length: 3 },
      (_, index) => ({
        id: `rgbd_${index}`,
        kind: "point_cloud",
        sequence: index,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        url: `/warehouse/live-map/flight/chunks/rgbd_${index}/download`,
        byte_size: 3,
      }),
    );

    const { result } = renderHook(() =>
      useLiveMapChunkCache("flight", chunks, null, { mode: "replay" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(requestFrame).toHaveBeenCalledTimes(1);
      frameCallbacks.shift()?.(performance.now());
    });

    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(3));
    expect(requestFrame).toHaveBeenCalledTimes(1);
  });

  it("caps concurrent chunk downloads", async () => {
    let active = 0;
    let maxActive = 0;
    const resolvers: Array<() => void> = [];
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          active += 1;
          maxActive = Math.max(maxActive, active);
          resolvers.push(() => {
            active -= 1;
            resolve(
              new Response(new Uint8Array([1, 2, 3]), {
                status: 200,
              }),
            );
          });
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const chunks: WarehouseLiveVoxelChunk[] = Array.from({ length: 6 }, (_, index) => ({
      id: `rgbd_${String(index + 1).padStart(6, "0")}`,
      kind: "point_cloud",
      sequence: index + 1,
      source: "rgbd_colored",
      layer: "rgbd_colored",
      url: `/warehouse/live-map/flight/chunks/rgbd_${String(index + 1).padStart(6, "0")}/download`,
      byte_size: 3,
    }));

    const { result } = renderHook(() =>
      useLiveMapChunkCache("flight", chunks, null, {
        config: {
          raw_lidar: { enabled: true, max_hz: 1, voxel_size: 0, max_points: 100 },
          frontend: {
            max_concurrent_chunk_downloads: 2,
            max_points_per_layer: 100,
          },
          preferred_layer: "rgbd_colored",
        },
      }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    while (resolvers.length > 0) {
      await act(async () => {
        resolvers.shift()?.();
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
    }
    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(6));
    expect(maxActive).toBeLessThanOrEqual(2);
  });

  it("does not treat a 304 response as an empty chunk body", async () => {
    const body = new Uint8Array([11, 22, 33]).buffer;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(body, {
          status: 200,
          headers: { ETag: '"etag-live"' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(null, {
          status: 304,
          headers: { ETag: '"etag-live"' },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const chunk: WarehouseLiveVoxelChunk = {
      id: "rgbd_000001",
      kind: "point_cloud",
      sequence: 1,
      source: "rgbd_colored",
      layer: "rgbd_colored",
      url: "/warehouse/live-map/flight/chunks/rgbd_000001/download",
      byte_size: 3,
      checksum_sha256: "deadbeef",
    };

    const { result, rerender } = renderHook(
      ({ chunks }) => useLiveMapChunkCache("flight", chunks),
      { initialProps: { chunks: [chunk] } },
    );

    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(1));
    expect(result.current.cachedChunks[0].bytes).toBe(3);

    rerender({ chunks: [{ ...chunk }] });
    await waitFor(() => expect(result.current.cachedChunks).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("mergeUpdate", () => {
  it("accumulates multiple chunks instead of replacing prior chunks", () => {
    const base = {
      chunksById: new Map<string, WarehouseLiveVoxelChunk>(),
      scanPath: [],
    };
    const first = mergeUpdate(base, {
      type: "live_map_update",
      flight_id: "flight_a",
      timestamp: "2026-01-01T00:00:00Z",
      frame_id: "map",
      pose: { x_m: 0, y_m: 0, z_m: 0, frame_id: "map" },
      changed_chunks: [
        {
          id: "rgbd_000001",
          kind: "point_cloud",
          sequence: 1,
          source: "rgbd_colored",
          layer: "rgbd_colored",
        },
      ],
      removed_chunk_ids: [],
      scan_path_sample: [],
      health: {
        stale_costmap: false,
        missing_mesh: true,
        missing_point_cloud: false,
        nvblox_ready: false,
        mapping_recording: true,
        stack_running: true,
      },
    });
    const second = mergeUpdate(first, {
      type: "live_map_update",
      flight_id: "flight_a",
      timestamp: "2026-01-01T00:00:01Z",
      frame_id: "map",
      pose: { x_m: 0, y_m: 0, z_m: 0, frame_id: "map" },
      changed_chunks: [
        {
          id: "rgbd_000002",
          kind: "point_cloud",
          sequence: 2,
          source: "rgbd_colored",
          layer: "rgbd_colored",
        },
      ],
      removed_chunk_ids: [],
      scan_path_sample: [],
      health: {
        stale_costmap: false,
        missing_mesh: true,
        missing_point_cloud: false,
        nvblox_ready: false,
        mapping_recording: true,
        stack_running: true,
      },
    });

    expect(second.chunksById.size).toBe(2);
  });

  it("merges websocket snapshots into existing live state", () => {
    const existing = {
      chunksById: new Map([
        [
          "rgbd_colored:rgbd_000001",
          {
            id: "rgbd_000001",
            kind: "point_cloud" as const,
            sequence: 1,
            source: "rgbd_colored" as const,
            layer: "rgbd_colored" as const,
          },
        ],
      ]),
      scanPath: [],
    };
    const merged = applyWarehouseLiveMapMessage(existing, {
      type: "live_map_snapshot",
      flight_id: "flight_a",
      status: "live",
      updates: [
        {
          type: "live_map_update",
          flight_id: "flight_a",
          timestamp: "2026-01-01T00:00:01Z",
          frame_id: "map",
          pose: { x_m: 0, y_m: 0, z_m: 0, frame_id: "map" },
          changed_chunks: [
            {
              id: "rgbd_000002",
              kind: "point_cloud",
              sequence: 2,
              source: "rgbd_colored",
              layer: "rgbd_colored",
            },
          ],
          removed_chunk_ids: [],
          scan_path_sample: [],
          health: {
            stale_costmap: false,
            missing_mesh: true,
            missing_point_cloud: false,
            nvblox_ready: false,
            mapping_recording: true,
            stack_running: true,
          },
        },
      ],
    });

    expect(merged.chunksById.size).toBe(2);
  });
});

describe("selectDownloadableChunksPerLayer", () => {
  it("loads every replay manifest chunk", () => {
    const chunks: WarehouseLiveVoxelChunk[] = Array.from({ length: 140 }, (_, index) => ({
      id: `rgbd_${String(index + 1).padStart(6, "0")}`,
      kind: "point_cloud" as const,
      sequence: index + 1,
      source: "rgbd_colored" as const,
      layer: "rgbd_colored" as const,
      url: `/warehouse/live-map/flight/chunks/rgbd_${String(index + 1).padStart(6, "0")}/download`,
      byte_size: 1024,
    }));

    const selected = selectDownloadableChunksPerLayer(chunks, "replay");
    expect(selected).toHaveLength(140);
  });
});

describe("filterChunksForDownload", () => {
  it("skips raw mid360 chunks when the debug layer is hidden", () => {
    const chunks: WarehouseLiveVoxelChunk[] = [
      {
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        url: "/warehouse/live-map/flight/chunks/rgbd_000001/download",
        byte_size: 1000,
      },
      {
        id: "mid360_000286",
        kind: "point_cloud",
        sequence: 286,
        source: "mid360_raw",
        layer: "mid360_lidar",
        url: "/warehouse/live-map/flight/chunks/mid360_000286/download",
        byte_size: 339000,
      },
    ];

    const filtered = filterChunksForDownload(
      chunks,
      { ...DEFAULT_LAYER_VISIBILITY, mid360LiDAR: false },
      "rgbd_colored",
    );

    expect(filtered.map((chunk) => chunk.id)).toEqual(["rgbd_000001"]);
  });

  it("downloads every visible layer instead of only the preferred layer", () => {
    const chunks: WarehouseLiveVoxelChunk[] = [
      {
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        url: "/warehouse/live-map/flight/chunks/rgbd_000001/download",
        byte_size: 1000,
      },
      {
        id: "nvblox_esdf_00000001",
        kind: "esdf",
        sequence: 1,
        source: "nvblox_esdf",
        layer: "nvblox_esdf",
        url: "/warehouse/live-map/flight/chunks/nvblox_esdf_00000001/download",
        byte_size: 2000,
      },
    ];

    const filtered = filterChunksForDownload(
      chunks,
      {
        ...DEFAULT_LAYER_VISIBILITY,
        rgbdColored: true,
        nvbloxEsdf: true,
      },
      "rgbd_colored",
    );

    expect(filtered.map((chunk) => chunk.id).sort()).toEqual([
      "nvblox_esdf_00000001",
      "rgbd_000001",
    ]);
  });
});

describe("defaultLayerVisibilityForChunks", () => {
  it("prefers colored layers when rgbd chunks exist", () => {
    const chunks: WarehouseLiveVoxelChunk[] = [
      {
        id: "rgbd_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_colored",
        layer: "rgbd_colored",
        has_rgb: true,
      },
      {
        id: "mid360_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "mid360_raw",
        layer: "mid360_lidar",
      },
    ];

    expect(hasColoredMapLayers(chunks)).toBe(true);
    const visibility = defaultLayerVisibilityForChunks(chunks);
    expect(visibility.rgbdColored).toBe(true);
    expect(visibility.mid360LiDAR).toBe(false);
    expect(inferLayerKey(chunks[0])).toBe("rgbdColored");
  });

  it("enables mid360 when the saved map is raw lidar only", () => {
    const chunks: WarehouseLiveVoxelChunk[] = [
      {
        id: "mid360_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "mid360_raw",
        layer: "mid360_lidar",
      },
    ];

    const visibility = defaultLayerVisibilityForChunks(chunks);
    expect(visibility.mid360LiDAR).toBe(true);
    expect(visibility.rgbdColored).toBe(false);
    expect(visibility.nvbloxColor).toBe(false);
  });

  it("labels and prefers RGB-D XYZ geometry when real RGB fields are absent", () => {
    const chunks: WarehouseLiveVoxelChunk[] = [
      {
        id: "rgbd_xyz_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "rgbd_xyz_uncolored",
        layer: "rgbd_xyz_uncolored",
        has_rgb: false,
      },
      {
        id: "nvblox_color_000001",
        kind: "point_cloud",
        sequence: 1,
        source: "nvblox_color",
        layer: "nvblox_color",
        has_rgb: true,
      },
    ];

    const visibility = defaultLayerVisibilityForChunks(chunks, {
      rgbd_cloud_available: true,
      rgbd_has_rgb: false,
      default_view_layer: "rgbd_xyz_uncolored",
      diagnostic_nvblox_layers: ["nvblox_color"],
    });

    expect(inferLayerKey(chunks[0])).toBe("rgbdDepth");
    expect(visibility.rgbdDepth).toBe(true);
    expect(visibility.rgbdColored).toBe(false);
    expect(visibility.nvbloxColor).toBe(false);
  });

  it("uses ESDF fallback but does not auto-enable internal TSDF blocks", () => {
    const visibility = defaultLayerVisibilityForChunks([], {
      chunk_counts: { nvblox_esdf: 12, nvblox_tsdf: 3 },
    });
    expect(visibility.nvbloxEsdf).toBe(true);
    expect(visibility.nvbloxTsdf).toBe(false);
    expect(visibility.rgbdColored).toBe(false);
  });

  it("marks layers with manifest chunk counts as available", () => {
    const availability = chunksAvailableByLayer([], {
      map_quality: "nvblox_esdf",
      chunk_counts: {
        rgbd_colored: 90,
        nvblox_esdf: 22,
      },
      point_counts: {},
    });

    expect(availability.rgbdColored).toBe(90);
    expect(availability.nvbloxEsdf).toBe(22);
    expect(
      layerHasStoredChunks("nvbloxEsdf", [], {
        chunk_counts: { nvblox_esdf: 22 },
      }),
    ).toBe(true);
  });
});
