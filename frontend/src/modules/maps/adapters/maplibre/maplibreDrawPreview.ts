import type { Map as MapLibreMapInstance } from "maplibre-gl";
import maplibregl from "maplibre-gl";
import {
  closeRing,
  shapePreview,
  type ShapeDrawMode,
} from "../../utils/drawingShapes";
import {
  drawFillLayerId,
  drawLineLayerId,
  drawPointLayerId,
  drawSourceId,
  type FlatDrawMode,
  type LonLat,
  type MapFeature,
} from "./maplibreMapTypes";

export function syncMapLibreDrawPreview(
  map: MapLibreMapInstance,
  mode: FlatDrawMode,
  coords: LonLat[],
) {
  if (!map.isStyleLoaded()) return;

  const previewCoords = shapePreview(mode, coords);
  const features: MapFeature[] = coords.map(([lng, lat]) => ({
    type: "Feature",
    properties: { kind: "point" },
    geometry: { type: "Point", coordinates: [lng, lat] },
  }));

  if (mode === "polyline" && previewCoords.length >= 2) {
    features.push({
      type: "Feature",
      properties: { kind: "line" },
      geometry: { type: "LineString", coordinates: previewCoords },
    });
  }

  if (
    ["polygon", "rectangle", "circle", "triangle", "freehand"].includes(mode) &&
    previewCoords.length >= 3
  ) {
    features.push({
      type: "Feature",
      properties: { kind: "polygon" },
      geometry: { type: "Polygon", coordinates: [closeRing(previewCoords)] },
    });
  }

  const data = { type: "FeatureCollection" as const, features };
  const source = map.getSource(drawSourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }

  map.addSource(drawSourceId, { type: "geojson", data });
  map.addLayer({
    id: drawFillLayerId,
    type: "fill",
    source: drawSourceId,
    filter: ["==", ["get", "kind"], "polygon"],
    paint: { "fill-color": "#1976d2", "fill-opacity": 0.16 },
  });
  map.addLayer({
    id: drawLineLayerId,
    type: "line",
    source: drawSourceId,
    filter: ["in", ["get", "kind"], ["literal", ["line", "polygon"]]],
    paint: {
      "line-color": "#1976d2",
      "line-width": 3,
      "line-dasharray": [2, 2],
    },
  });
  map.addLayer({
    id: drawPointLayerId,
    type: "circle",
    source: drawSourceId,
    filter: ["==", ["get", "kind"], "point"],
    paint: {
      "circle-radius": 5,
      "circle-color": "#1976d2",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
}

export function clearMapLibreDrawPreview(map: MapLibreMapInstance) {
  syncMapLibreDrawPreview(map, "none" as ShapeDrawMode, []);
}
