import { describe, expect, it } from "vitest";
import {
  accessibleFeatures,
  buildAgricultureMapData,
  featureCenter,
  normalizeGeoJson,
} from "./data";

describe("agriculture analysis map data", () => {
  it("normalizes and centroid-indexes more than 5,000 observations", () => {
    const features = Array.from({ length: 5_001 }, (_, index) => ({
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [[
          [4 + index * 0.000001, 50],
          [4.0001 + index * 0.000001, 50],
          [4.0001 + index * 0.000001, 50.0001],
          [4 + index * 0.000001, 50],
        ]],
      },
      properties: {
        observation_id: `obs-${index}`,
        observation_type: "weed",
        severity: index / 5_001,
      },
    }));

    const data = buildAgricultureMapData({
      observations: { type: "FeatureCollection", features },
      selectedId: "obs-5000",
    });

    expect(data.observationCentroids.features).toHaveLength(5_001);
    expect(data.observationShapes.features).toHaveLength(5_001);
    expect(data.selection.features[0]?.properties?.observation_id).toBe(
      "obs-5000",
    );
    expect(accessibleFeatures({ features })).toHaveLength(5_001);
  });

  it("filters invalid geometry and does not expose aggregate cells as findings", () => {
    const input = {
      features: [
        { type: "Feature", geometry: {}, properties: { id: "invalid" } },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [4, 50] },
          properties: { id: "cluster-1", cluster: true },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [5, 51] },
          properties: { observation_id: "obs-1" },
        },
      ],
    };
    expect(normalizeGeoJson(input).features).toHaveLength(2);
    expect(accessibleFeatures(input).map((feature) => feature.id)).toEqual([
      "obs-1",
    ]);
  });

  it("calculates a stable center for polygon selection focus", () => {
    const feature = normalizeGeoJson({
      features: [{
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
        },
        properties: {},
      }],
    }).features[0];
    expect(feature && featureCenter(feature)).toEqual([0.8, 0.8]);
  });
});
