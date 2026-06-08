import { describe, expect, it } from "vitest";
import { mergeReplaySnapshot } from "../utils/mergeReplaySnapshot";
import type { WarehouseLiveMapSnapshot } from "../api/warehouseLiveMapApi";

describe("mergeReplaySnapshot", () => {
  it("keeps every chunk from the snapshot without trimming", () => {
    const snapshot: WarehouseLiveMapSnapshot = {
      type: "live_map_snapshot",
      flight_id: "flight-1",
      status: "finalized",
      updates: [
        {
          type: "live_map_update",
          flight_id: "flight-1",
          timestamp: "2026-06-08T00:00:00.000Z",
          frame_id: "map",
          pose: { x_m: 0, y_m: 0, z_m: 0, frame_id: "map" },
          changed_chunks: Array.from({ length: 120 }, (_, index) => ({
            id: `chunk-${index}`,
            kind: "point_cloud" as const,
            sequence: index,
            preview_points_m: [[index, 0, 0]],
          })),
          removed_chunk_ids: [],
          scan_path_sample: [],
          health: {
            stale_costmap: false,
            missing_mesh: true,
            missing_point_cloud: false,
            nvblox_ready: true,
            mapping_recording: false,
            stack_running: false,
          },
        },
      ],
    };

    const merged = mergeReplaySnapshot(snapshot);
    expect(merged.chunks).toHaveLength(120);
    expect(merged.chunks[0]?.id).toBe("chunk-0");
    expect(merged.chunks.at(-1)?.id).toBe("chunk-119");
  });
});
