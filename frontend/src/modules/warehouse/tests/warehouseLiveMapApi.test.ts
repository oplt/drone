import { describe, expect, it } from "vitest";
import {
  isWarehouseLiveMapSnapshot,
  isWarehouseLiveMapUpdate,
  type WarehouseLiveMapSnapshot,
} from "../api/warehouseLiveMapApi";
import { applyWarehouseLiveMapMessage } from "../hooks/useWarehouseLiveVoxelMap";

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
});
