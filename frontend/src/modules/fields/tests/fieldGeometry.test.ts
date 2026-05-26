import { describe, expect, it } from "vitest";
import { computeCentroid, stripClosedRing } from "../utils/fieldGeometry";

describe("fieldGeometry", () => {
  it("strips duplicate closing coordinate", () => {
    const ring = stripClosedRing([
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 0],
    ]);
    expect(ring).toHaveLength(3);
  });

  it("computes centroid for simple square", () => {
    const centroid = computeCentroid([
      [0, 0],
      [2, 0],
      [2, 2],
      [0, 2],
    ]);
    expect(centroid?.lat).toBeCloseTo(1, 1);
    expect(centroid?.lng).toBeCloseTo(1, 1);
  });
});
