import { describe, expect, it } from "vitest";
import { computeCentroid, computeRingMapViewport, ringLatLngBounds, stripClosedRing } from "../utils/fieldGeometry";

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

  it("computes map viewport for geofence ring", () => {
    const viewport = computeRingMapViewport([
      [4.35, 50.84],
      [4.36, 50.84],
      [4.36, 50.85],
      [4.35, 50.85],
    ]);
    expect(viewport?.center.lat).toBeCloseTo(50.845, 2);
    expect(viewport?.center.lng).toBeCloseTo(4.355, 2);
    expect(viewport?.zoom).toBeGreaterThan(10);
  });

  it("computes lat lng bounds for geofence ring", () => {
    const bounds = ringLatLngBounds([
      [4.35, 50.84],
      [4.36, 50.84],
      [4.36, 50.85],
      [4.35, 50.85],
    ]);
    expect(bounds).toEqual({
      south: 50.84,
      west: 4.35,
      north: 50.85,
      east: 4.36,
    });
  });
});
