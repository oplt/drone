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
});
