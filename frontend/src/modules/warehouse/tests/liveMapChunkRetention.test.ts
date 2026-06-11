import { describe, expect, it } from "vitest";
import {
  limitChunksPerLayer,
  selectDownloadableChunksPerLayer,
} from "../utils/liveMapChunkRetention";
import type { WarehouseLiveVoxelChunk } from "../api/warehouseLiveMapApi";

function chunk(
  id: string,
  sequence: number,
  layer: WarehouseLiveVoxelChunk["layer"],
): WarehouseLiveVoxelChunk {
  return {
    id,
    kind: "point_cloud",
    sequence,
    layer,
    url: `/warehouse/live-map/flight/chunks/${id}/download`,
    byte_size: 1024,
  };
}

describe("liveMapChunkRetention", () => {
  it("keeps latest chunks per layer instead of global sequence", () => {
    const mid360 = Array.from({ length: 200 }, (_, index) =>
      chunk(`mid360_${String(index + 1).padStart(6, "0")}`, index + 1, "mid360_lidar"),
    );
    const rgbd = Array.from({ length: 80 }, (_, index) =>
      chunk(`rgbd_${String(index + 1).padStart(6, "0")}`, index + 1, "rgbd_colored"),
    );

    const retained = limitChunksPerLayer([...mid360, ...rgbd]);

    expect(retained.filter((item) => item.layer === "rgbd_colored")).toHaveLength(80);
    expect(retained.filter((item) => item.layer === "mid360_lidar")).toHaveLength(32);
    expect(retained.some((item) => item.id === "rgbd_000001")).toBe(true);
    expect(retained.some((item) => item.id === "rgbd_000080")).toBe(true);
    expect(retained.some((item) => item.id === "mid360_000200")).toBe(true);
    expect(retained.some((item) => item.id === "mid360_000001")).toBe(false);
  });

  it("selects downloadable chunks per layer in live mode", () => {
    const mid360 = Array.from({ length: 60 }, (_, index) =>
      chunk(`mid360_${String(index + 1).padStart(6, "0")}`, index + 1, "mid360_lidar"),
    );
    const rgbd = Array.from({ length: 60 }, (_, index) =>
      chunk(`rgbd_${String(index + 1).padStart(6, "0")}`, index + 1, "rgbd_colored"),
    );

    const selected = selectDownloadableChunksPerLayer(
      [...mid360, ...rgbd],
      "live",
      { maxCachedChunksPerLayer: 48 },
    );

    expect(selected.filter((item) => item.layer === "rgbd_colored")).toHaveLength(48);
    expect(selected.filter((item) => item.layer === "mid360_lidar")).toHaveLength(8);
    expect(selected.some((item) => item.id.startsWith("rgbd_"))).toBe(true);
  });

  it("keeps full colored scan history by default", () => {
    const rgbd = Array.from({ length: 500 }, (_, index) =>
      chunk(`rgbd_${String(index + 1).padStart(6, "0")}`, index + 1, "rgbd_colored"),
    );

    const retained = limitChunksPerLayer(rgbd);
    const selected = selectDownloadableChunksPerLayer(rgbd, "live");

    expect(retained).toHaveLength(500);
    expect(selected).toHaveLength(500);
    expect(retained[0].id).toBe("rgbd_000001");
  });
});
