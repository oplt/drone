import { describe, expect, it } from "vitest";

import {
  computeFieldCameraView,
  computeRingCentroid,
  normalizeLonLatLine,
  normalizeLonLatRing,
  zoomToHeightMeters,
} from "../utils/cesiumCameraGeometry";

describe("Cesium camera geometry", () => {
  it("converts map zoom to a bounded camera height", () => {
    expect(zoomToHeightMeters(0)).toBe(10_000_000);
    expect(zoomToHeightMeters(10)).toBe(19_531);
    expect(zoomToHeightMeters(30)).toBe(19);
  });

  it("removes invalid positions and a duplicate closing vertex", () => {
    const coordinates = [
      [4, 50],
      [Number.NaN, 51],
      [5, 50],
      [5, 51],
      [4, 50],
    ] as [number, number][];

    expect(normalizeLonLatLine(coordinates)).toHaveLength(4);
    expect(normalizeLonLatRing(coordinates)).toEqual([
      [4, 50],
      [5, 50],
      [5, 51],
    ]);
  });

  it("computes polygon and degenerate-ring centroids", () => {
    expect(computeRingCentroid([[0, 0], [2, 0], [2, 2], [0, 2]])).toEqual({
      lat: 1,
      lng: 1,
    });
    expect(computeRingCentroid([[0, 0], [1, 0], [2, 0]])).toEqual({
      lat: 0,
      lng: 1,
    });
  });

  it("fits camera height to field span within safety bounds", () => {
    const view = computeFieldCameraView([
      [4, 50],
      [4.001, 50],
      [4.001, 50.001],
      [4, 50.001],
    ]);
    expect(view?.center.lat).toBeCloseTo(50.0005);
    expect(view?.center.lng).toBeCloseTo(4.0005);
    expect(view?.topHeight).toBe(267);
    expect(computeFieldCameraView([[0, 0], [1, 0]])).toBeNull();
  });
});
