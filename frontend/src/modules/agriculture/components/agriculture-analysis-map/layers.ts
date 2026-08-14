import maplibregl, {
  type ExpressionSpecification,
  type Map as MapLibreMap,
} from "maplibre-gl";
import { featureId } from "./data";
import type {
  AgricultureMapData,
  AgricultureMapFeature,
  AgricultureMapLayerKey,
  AgricultureMapLayerVisibility,
} from "./types";

export const AGRICULTURE_MAP_SOURCES = {
  fieldBoundary: "agriculture-field-boundary",
  flightPath: "agriculture-flight-path",
  observationCentroids: "agriculture-observation-centroids",
  observationShapes: "agriculture-observation-shapes",
  severityAreas: "agriculture-severity-areas",
  interventionZones: "agriculture-intervention-zones",
  temporalChanges: "agriculture-temporal-changes",
  selection: "agriculture-selection",
} as const;

export const AGRICULTURE_MAP_LAYERS = {
  fieldFill: "agriculture-field-fill",
  fieldLine: "agriculture-field-line",
  flightPath: "agriculture-flight-path-line",
  cluster: "agriculture-observation-clusters",
  clusterCount: "agriculture-observation-cluster-count",
  observationPoint: "agriculture-observation-points",
  observationShapeFill: "agriculture-observation-shape-fill",
  observationShapeLine: "agriculture-observation-shape-line",
  severityFill: "agriculture-severity-fill",
  severityLine: "agriculture-severity-line",
  heatmap: "agriculture-observation-heatmap",
  zoneFill: "agriculture-zone-fill",
  zoneLine: "agriculture-zone-line",
  temporalFill: "agriculture-temporal-change-fill",
  temporalLine: "agriculture-temporal-change-line",
  selectionFill: "agriculture-selection-fill",
  selectionLine: "agriculture-selection-line",
  selectionPoint: "agriculture-selection-point",
} as const;

const severityColor: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["coalesce", ["to-number", ["get", "severity"]], 0],
  0,
  "#2e7d32",
  0.5,
  "#ed6c02",
  1,
  "#c62828",
];

const temporalColor: ExpressionSpecification = [
  "match",
  ["get", "state"],
  "new", "#c62828",
  "resolved", "#2e7d32",
  "expanding", "#ef6c00",
  "improving", "#00897b",
  "stable", "#1565c0",
  "#546e7a",
];

const zoneColor: ExpressionSpecification = [
  "match",
  ["get", "status"],
  "approved", "#2e7d32",
  "rejected", "#616161",
  "#7b1fa2",
];

export const DEFAULT_AGRICULTURE_MAP_VISIBILITY: AgricultureMapLayerVisibility = {
  fieldBoundary: true,
  flightPath: true,
  observations: true,
  severity: true,
  heatmap: false,
  temporalChanges: true,
  interventionZones: true,
};

export function addAgricultureMapLayers(map: MapLibreMap, data: AgricultureMapData) {
  map.addSource(AGRICULTURE_MAP_SOURCES.fieldBoundary, { type: "geojson", data: data.fieldBoundary });
  map.addSource(AGRICULTURE_MAP_SOURCES.flightPath, { type: "geojson", data: data.flightPath });
  map.addSource(AGRICULTURE_MAP_SOURCES.observationCentroids, {
    type: "geojson",
    data: data.observationCentroids,
    cluster: true,
    clusterMaxZoom: 14,
    clusterRadius: 46,
  });
  map.addSource(AGRICULTURE_MAP_SOURCES.observationShapes, { type: "geojson", data: data.observationShapes });
  map.addSource(AGRICULTURE_MAP_SOURCES.severityAreas, { type: "geojson", data: data.severityAreas });
  map.addSource(AGRICULTURE_MAP_SOURCES.interventionZones, { type: "geojson", data: data.interventionZones });
  map.addSource(AGRICULTURE_MAP_SOURCES.temporalChanges, { type: "geojson", data: data.temporalChanges });
  map.addSource(AGRICULTURE_MAP_SOURCES.selection, { type: "geojson", data: data.selection });

  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.fieldFill, type: "fill", source: AGRICULTURE_MAP_SOURCES.fieldBoundary, paint: { "fill-color": "#2e7d32", "fill-opacity": 0.08 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.fieldLine, type: "line", source: AGRICULTURE_MAP_SOURCES.fieldBoundary, paint: { "line-color": "#1b5e20", "line-width": 2 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.severityFill, type: "fill", source: AGRICULTURE_MAP_SOURCES.severityAreas, paint: { "fill-color": severityColor, "fill-opacity": 0.32 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.severityLine, type: "line", source: AGRICULTURE_MAP_SOURCES.severityAreas, paint: { "line-color": severityColor, "line-width": 1.5 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.zoneFill, type: "fill", source: AGRICULTURE_MAP_SOURCES.interventionZones, paint: { "fill-color": zoneColor, "fill-opacity": 0.2 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.zoneLine, type: "line", source: AGRICULTURE_MAP_SOURCES.interventionZones, paint: { "line-color": zoneColor, "line-width": 2, "line-dasharray": [2, 1] } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.temporalFill, type: "fill", source: AGRICULTURE_MAP_SOURCES.temporalChanges, paint: { "fill-color": temporalColor, "fill-opacity": 0.36 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.temporalLine, type: "line", source: AGRICULTURE_MAP_SOURCES.temporalChanges, paint: { "line-color": temporalColor, "line-width": 2.5 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.observationShapeFill, type: "fill", source: AGRICULTURE_MAP_SOURCES.observationShapes, minzoom: 13, paint: { "fill-color": severityColor, "fill-opacity": 0.42 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.observationShapeLine, type: "line", source: AGRICULTURE_MAP_SOURCES.observationShapes, minzoom: 13, paint: { "line-color": severityColor, "line-width": 2 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.heatmap, type: "heatmap", source: AGRICULTURE_MAP_SOURCES.observationCentroids, filter: ["!", ["has", "point_count"]], maxzoom: 17, paint: { "heatmap-weight": ["coalesce", ["to-number", ["get", "severity"]], 0.25], "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 16, 2.2], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 12, 16, 28], "heatmap-opacity": 0.72, "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(46,125,50,0)", 0.35, "#66bb6a", 0.65, "#f9a825", 1, "#c62828"] } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.cluster, type: "circle", source: AGRICULTURE_MAP_SOURCES.observationCentroids, filter: ["has", "point_count"], paint: { "circle-color": ["step", ["get", "point_count"], "#2e7d32", 20, "#ed6c02", 100, "#c62828"], "circle-radius": ["step", ["get", "point_count"], 17, 20, 22, 100, 28], "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.clusterCount, type: "symbol", source: AGRICULTURE_MAP_SOURCES.observationCentroids, filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 }, paint: { "text-color": "#ffffff" } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.observationPoint, type: "circle", source: AGRICULTURE_MAP_SOURCES.observationCentroids, filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "source_geometry_type"], "Point"]], paint: { "circle-color": severityColor, "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.flightPath, type: "line", source: AGRICULTURE_MAP_SOURCES.flightPath, paint: { "line-color": "#1565c0", "line-width": 3, "line-opacity": 0.9 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.selectionFill, type: "fill", source: AGRICULTURE_MAP_SOURCES.selection, paint: { "fill-color": "#ffffff", "fill-opacity": 0.12 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.selectionLine, type: "line", source: AGRICULTURE_MAP_SOURCES.selection, paint: { "line-color": "#0d47a1", "line-width": 4 } });
  map.addLayer({ id: AGRICULTURE_MAP_LAYERS.selectionPoint, type: "circle", source: AGRICULTURE_MAP_SOURCES.selection, filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": "#ffffff", "circle-radius": 9, "circle-stroke-color": "#0d47a1", "circle-stroke-width": 4 } });
}

const visibilityLayers: Record<AgricultureMapLayerKey, string[]> = {
  fieldBoundary: [AGRICULTURE_MAP_LAYERS.fieldFill, AGRICULTURE_MAP_LAYERS.fieldLine],
  flightPath: [AGRICULTURE_MAP_LAYERS.flightPath],
  observations: [AGRICULTURE_MAP_LAYERS.cluster, AGRICULTURE_MAP_LAYERS.clusterCount, AGRICULTURE_MAP_LAYERS.observationPoint],
  severity: [AGRICULTURE_MAP_LAYERS.observationShapeFill, AGRICULTURE_MAP_LAYERS.observationShapeLine, AGRICULTURE_MAP_LAYERS.severityFill, AGRICULTURE_MAP_LAYERS.severityLine],
  heatmap: [AGRICULTURE_MAP_LAYERS.heatmap],
  temporalChanges: [AGRICULTURE_MAP_LAYERS.temporalFill, AGRICULTURE_MAP_LAYERS.temporalLine],
  interventionZones: [AGRICULTURE_MAP_LAYERS.zoneFill, AGRICULTURE_MAP_LAYERS.zoneLine],
};

export function applyAgricultureMapVisibility(map: MapLibreMap, visibility: AgricultureMapLayerVisibility) {
  Object.entries(visibilityLayers).forEach(([key, layerIds]) => {
    layerIds.forEach((layerId) => map.setLayoutProperty(layerId, "visibility", visibility[key as AgricultureMapLayerKey] ? "visible" : "none"));
  });
}

export function updateAgricultureMapData(map: MapLibreMap, data: AgricultureMapData) {
  Object.entries(AGRICULTURE_MAP_SOURCES).forEach(([key, sourceId]) => {
    (map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined)?.setData(data[key as keyof AgricultureMapData]);
  });
}

export async function handleAgricultureMapClick(map: MapLibreMap, point: maplibregl.PointLike, onSelect?: (id: string) => void) {
  const cluster = map.queryRenderedFeatures(point, { layers: [AGRICULTURE_MAP_LAYERS.cluster] })[0];
  const clusterId = Number(cluster?.properties?.cluster_id);
  if (cluster && Number.isFinite(clusterId) && cluster.geometry.type === "Point") {
    const source = map.getSource(AGRICULTURE_MAP_SOURCES.observationCentroids) as maplibregl.GeoJSONSource;
    const zoom = await source.getClusterExpansionZoom(clusterId);
    map.easeTo({ center: cluster.geometry.coordinates as [number, number], zoom });
    return;
  }
  const feature = map.queryRenderedFeatures(point, { layers: [AGRICULTURE_MAP_LAYERS.observationPoint, AGRICULTURE_MAP_LAYERS.observationShapeFill, AGRICULTURE_MAP_LAYERS.severityFill, AGRICULTURE_MAP_LAYERS.temporalFill, AGRICULTURE_MAP_LAYERS.zoneFill] })[0] as AgricultureMapFeature | undefined;
  if (feature?.properties?.cluster === true) return;
  const id = feature ? featureId(feature) : null;
  if (id) onSelect?.(id);
}
