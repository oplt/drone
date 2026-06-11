import { describe, expect, it } from "vitest";
import { toRenderChunks } from "../utils/liveMapRenderModel";

describe("live map render model", () => {
  it("uses real chunk bounding boxes when present", () => {
    const chunks = toRenderChunks([
      {
        id: "c1",
        kind: "mesh",
        sequence: 3,
        bbox_local_m: [0, 1, 2, 2, 5, 8],
        point_count: 12,
        url: "/warehouse/live-map/f/chunks/c1/download",
      },
    ]);

    expect(chunks[0].center).toEqual([1, 3, 5]);
    expect(chunks[0].size).toEqual([2, 4, 6]);
    expect(chunks[0].hasGeometry).toBe(true);
  });

  it("uses preview points when provided", () => {
    const chunks = toRenderChunks([
      {
        id: "c2",
        kind: "point_cloud",
        sequence: 1,
        preview_points_m: [
          [1, 2, 0.1],
          [1.2, 2.1, 0.2],
        ],
        point_count: 2,
      },
    ]);

    expect(chunks[0].previewPoints).toEqual([
      [1, 2, 0.1],
      [1.2, 2.1, 0.2],
    ]);
    expect(chunks[0].hasGeometry).toBe(true);
  });

  it("does not drop older scan chunks before rendering", () => {
    const chunks = toRenderChunks(
      Array.from({ length: 250 }, (_, index) => ({
        id: `rgbd_${String(index + 1).padStart(6, "0")}`,
        kind: "point_cloud" as const,
        sequence: index + 1,
        point_count: 1,
        preview_points_m: [[index, 0, 0]],
      })),
    );

    expect(chunks).toHaveLength(250);
    expect(chunks[0].id).toBe("rgbd_000001");
  });
});
