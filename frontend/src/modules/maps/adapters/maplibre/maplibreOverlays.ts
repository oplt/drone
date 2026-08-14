import type { Map as MapLibreMapInstance } from "maplibre-gl";
import maplibregl from "maplibre-gl";
import {
  overlayFillLayerId,
  overlayLineLayerId,
  overlaySourceId,
  type FlatDrawMode,
  type LonLat,
  type MapFeature,
  type SavedFieldBoundary,
} from "./maplibreMapTypes";

export type MapLibreOverlaySyncArgs = {
  drawMode: FlatDrawMode;
  savedFields: SavedFieldBoundary[];
  selectedFieldId: number | null;
  fieldBoundary: LonLat[] | null;
  drawnBoundarySelected: boolean;
  exclusionZones: LonLat[][];
  plannedRoute: LonLat[] | null;
};

export function syncMapLibreOverlays(
  map: MapLibreMapInstance,
  args: MapLibreOverlaySyncArgs,
) {
  if (!map.isStyleLoaded()) return;

  const {
    drawMode,
    savedFields,
    selectedFieldId,
    fieldBoundary,
    drawnBoundarySelected,
    exclusionZones,
    plannedRoute,
  } = args;

  const features: MapFeature[] = [];

  savedFields.forEach((field) => {
    if (field.ring.length < 3) return;
    features.push({
      type: "Feature",
      properties: {
        kind: "saved-field",
        fieldId: field.id,
        selected: field.id === selectedFieldId,
      },
      geometry: {
        type: "Polygon",
        coordinates: [[...field.ring, field.ring[0]]],
      },
    });
  });

  if (drawMode === "none" && fieldBoundary && fieldBoundary.length >= 3) {
    features.push({
      type: "Feature",
      properties: { kind: "field", selected: drawnBoundarySelected },
      geometry: {
        type: "Polygon",
        coordinates: [[...fieldBoundary, fieldBoundary[0]]],
      },
    });
  }

  exclusionZones.forEach((zone) => {
    if (zone.length < 3) return;
    features.push({
      type: "Feature",
      properties: { kind: "exclusion" },
      geometry: { type: "Polygon", coordinates: [[...zone, zone[0]]] },
    });
  });

  if (plannedRoute && plannedRoute.length >= 2) {
    features.push({
      type: "Feature",
      properties: { kind: "planned" },
      geometry: { type: "LineString", coordinates: plannedRoute },
    });
  }

  const data = { type: "FeatureCollection" as const, features };
  const source = map.getSource(overlaySourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }

  map.addSource(overlaySourceId, { type: "geojson", data });
  map.addLayer({
    id: overlayFillLayerId,
    type: "fill",
    source: overlaySourceId,
    filter: ["==", ["geometry-type"], "Polygon"],
    paint: {
      "fill-color": [
        "case",
        ["==", ["get", "kind"], "exclusion"],
        "#d32f2f",
        ["==", ["get", "selected"], true],
        "#1976d2",
        "#1565c0",
      ],
      "fill-opacity": [
        "case",
        ["==", ["get", "kind"], "exclusion"],
        0.24,
        ["==", ["get", "kind"], "saved-field"],
        0.08,
        0.12,
      ],
    },
  });
  map.addLayer({
    id: overlayLineLayerId,
    type: "line",
    source: overlaySourceId,
    paint: {
      "line-color": [
        "case",
        ["==", ["get", "kind"], "exclusion"],
        "#b71c1c",
        ["==", ["get", "kind"], "planned"],
        "#2e7d32",
        ["==", ["get", "selected"], true],
        "#1976d2",
        "#1565c0",
      ],
      "line-width": [
        "case",
        ["==", ["get", "kind"], "planned"],
        4,
        [
          "all",
          ["==", ["get", "kind"], "field"],
          ["==", ["get", "selected"], true],
        ],
        4,
        ["==", ["get", "selected"], true],
        4,
        2,
      ],
    },
  });
}
