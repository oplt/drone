import type { Map as MapLibreMap, PointLike } from "maplibre-gl";
import { describe, expect, it, vi } from "vitest";
import {
  AGRICULTURE_MAP_LAYERS,
  AGRICULTURE_MAP_SOURCES,
  applyAgricultureMapVisibility,
  handleAgricultureMapClick,
} from "./layers";

describe("agriculture analysis map interactions", () => {
  const point = { x: 1, y: 1 } as unknown as PointLike;

  it("expands a native observation cluster", async () => {
    const getClusterExpansionZoom = vi.fn().mockResolvedValue(17);
    const easeTo = vi.fn();
    const map = {
      queryRenderedFeatures: vi.fn().mockReturnValue([{
        geometry: { type: "Point", coordinates: [4, 50] },
        properties: { cluster_id: 42 },
      }]),
      getSource: vi.fn().mockReturnValue({ getClusterExpansionZoom }),
      easeTo,
    } as unknown as MapLibreMap;

    await handleAgricultureMapClick(map, point);

    expect(getClusterExpansionZoom).toHaveBeenCalledWith(42);
    expect(easeTo).toHaveBeenCalledWith({ center: [4, 50], zoom: 17 });
    expect(map.getSource).toHaveBeenCalledWith(
      AGRICULTURE_MAP_SOURCES.observationCentroids,
    );
  });

  it("returns the canonical observation id for a raw feature", async () => {
    const onSelect = vi.fn();
    const queryRenderedFeatures = vi
      .fn()
      .mockReturnValueOnce([])
      .mockReturnValueOnce([{
        type: "Feature",
        geometry: { type: "Point", coordinates: [4, 50] },
        properties: { observation_id: "obs-9" },
      }]);
    const map = { queryRenderedFeatures } as unknown as MapLibreMap;

    await handleAgricultureMapClick(map, point, onSelect);

    expect(onSelect).toHaveBeenCalledWith("obs-9");
  });

  it("applies independent visibility to analytical layers", () => {
    const setLayoutProperty = vi.fn();
    const map = { setLayoutProperty } as unknown as MapLibreMap;
    applyAgricultureMapVisibility(map, {
      fieldBoundary: true,
      flightPath: false,
      observations: true,
      severity: true,
      heatmap: false,
      temporalChanges: true,
      interventionZones: true,
    });
    expect(setLayoutProperty).toHaveBeenCalledWith(
      AGRICULTURE_MAP_LAYERS.flightPath,
      "visibility",
      "none",
    );
    expect(setLayoutProperty).toHaveBeenCalledWith(
      AGRICULTURE_MAP_LAYERS.heatmap,
      "visibility",
      "none",
    );
    expect(setLayoutProperty).toHaveBeenCalledWith(
      AGRICULTURE_MAP_LAYERS.cluster,
      "visibility",
      "visible",
    );
  });
});
