import type { Geometry, Position } from "geojson";
import type {
  AgricultureAccessibleFeature,
  AgricultureMapData,
  AgricultureMapFeature,
  AgricultureMapFeatureCollection,
  AgricultureMapGeoJson,
  AgricultureMapLayerVisibility,
} from "./types";

const EMPTY_COLLECTION: AgricultureMapFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

function isGeometry(value: unknown): value is Geometry {
  if (!value || typeof value !== "object") return false;
  const candidate = value as { type?: unknown; coordinates?: unknown };
  return (
    typeof candidate.type === "string" &&
    candidate.type !== "GeometryCollection" &&
    Array.isArray(candidate.coordinates)
  );
}

function normalizeFeature(value: Record<string, unknown>): AgricultureMapFeature | null {
  if (!isGeometry(value.geometry)) return null;
  const properties =
    value.properties && typeof value.properties === "object"
      ? (value.properties as Record<string, unknown>)
      : {};
  const feature: AgricultureMapFeature = {
    type: "Feature",
    geometry: value.geometry,
    properties,
  };
  if (typeof value.id === "string" || typeof value.id === "number") {
    feature.id = value.id;
  }
  return feature;
}

export function normalizeGeoJson(
  value?: AgricultureMapGeoJson | null,
): AgricultureMapFeatureCollection {
  if (!value?.features?.length) return EMPTY_COLLECTION;
  return {
    type: "FeatureCollection",
    features: value.features
      .map(normalizeFeature)
      .filter((feature): feature is AgricultureMapFeature => feature != null),
  };
}

export function featureId(feature: AgricultureMapFeature): string | null {
  const properties = feature.properties ?? {};
  const candidate =
    properties.observation_id ??
    properties.finding_id ??
    properties.change_id ??
    properties.zone_id ??
    properties.id ??
    feature.id;
  return typeof candidate === "string" || typeof candidate === "number"
    ? String(candidate)
    : null;
}

function positions(value: unknown, output: Position[] = []): Position[] {
  if (
    Array.isArray(value) &&
    value.length >= 2 &&
    typeof value[0] === "number" &&
    typeof value[1] === "number" &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  ) {
    output.push([value[0], value[1]]);
  } else if (Array.isArray(value)) {
    value.forEach((item) => positions(item, output));
  }
  return output;
}

export function featureCenter(feature: AgricultureMapFeature): Position | null {
  const points = positions(
    "coordinates" in feature.geometry ? feature.geometry.coordinates : [],
  );
  if (!points.length) return null;
  return [
    points.reduce((sum, point) => sum + point[0], 0) / points.length,
    points.reduce((sum, point) => sum + point[1], 0) / points.length,
  ];
}

function centroidFeature(feature: AgricultureMapFeature): AgricultureMapFeature | null {
  const center = featureCenter(feature);
  if (!center) return null;
  return {
    type: "Feature",
    id: feature.id,
    geometry: { type: "Point", coordinates: center },
    properties: {
      ...(feature.properties ?? {}),
      source_geometry_type: feature.geometry.type,
    },
  };
}

export function buildAgricultureMapData({
  observations,
  fieldBoundary,
  flightPath,
  severityAreas,
  interventionZones,
  temporalChanges,
  selectedId,
}: {
  observations: AgricultureMapGeoJson;
  fieldBoundary?: AgricultureMapGeoJson | null;
  flightPath?: AgricultureMapGeoJson | null;
  severityAreas?: AgricultureMapGeoJson | null;
  interventionZones?: AgricultureMapGeoJson | null;
  temporalChanges?: AgricultureMapGeoJson | null;
  selectedId?: string | null;
}): AgricultureMapData {
  const normalizedObservations = normalizeGeoJson(observations);
  const normalizedTemporalChanges = normalizeGeoJson(temporalChanges);
  const normalizedInterventionZones = normalizeGeoJson(interventionZones);
  const selection = selectedId
    ? [...normalizedObservations.features, ...normalizedTemporalChanges.features, ...normalizedInterventionZones.features].find(
        (feature) => featureId(feature) === selectedId,
      )
    : null;
  return {
    fieldBoundary: normalizeGeoJson(fieldBoundary),
    flightPath: normalizeGeoJson(flightPath),
    observationCentroids: {
      type: "FeatureCollection",
      features: normalizedObservations.features
        .map(centroidFeature)
        .filter((feature): feature is AgricultureMapFeature => feature != null),
    },
    observationShapes: {
      type: "FeatureCollection",
      features: normalizedObservations.features.filter(
        (feature) => feature.geometry.type !== "Point",
      ),
    },
    severityAreas: normalizeGeoJson(severityAreas),
    interventionZones: normalizedInterventionZones,
    temporalChanges: normalizedTemporalChanges,
    selection: {
      type: "FeatureCollection",
      features: selection ? [selection] : [],
    },
  };
}

export function accessibleFeatures(
  observations: AgricultureMapGeoJson,
): AgricultureAccessibleFeature[] {
  return normalizeGeoJson(observations).features.flatMap((feature) => {
    if (feature.properties?.cluster === true) return [];
    const id = featureId(feature);
    if (!id) return [];
    return [{
      id,
      label: String(
        feature.properties?.observation_type ??
        feature.properties?.name ??
        feature.properties?.category ??
        "Map feature",
      ).replaceAll("_", " "),
      severity: Math.max(0, Math.min(1, Number(feature.properties?.severity ?? 0))),
    }];
  });
}

export function accessibleMapFeatures(
  observations: AgricultureMapGeoJson,
  temporalChanges?: AgricultureMapGeoJson | null,
  interventionZones?: AgricultureMapGeoJson | null,
): AgricultureAccessibleFeature[] {
  return accessibleFeatures({
    type: "FeatureCollection",
    features: [
      ...(observations.features ?? []),
      ...(temporalChanges?.features ?? []),
      ...(interventionZones?.features ?? []),
    ],
  });
}

export function availableMapLayers(data: AgricultureMapData): AgricultureMapLayerVisibility {
  return {
    fieldBoundary: data.fieldBoundary.features.length > 0,
    flightPath: data.flightPath.features.length > 0,
    observations: data.observationCentroids.features.length > 0,
    severity: data.observationShapes.features.length > 0 || data.severityAreas.features.length > 0,
    heatmap: data.observationCentroids.features.length > 0,
    temporalChanges: data.temporalChanges.features.length > 0,
    interventionZones: data.interventionZones.features.length > 0,
  };
}

export function allMapPositions(data: AgricultureMapData): Position[] {
  return [
    data.fieldBoundary,
    data.flightPath,
    data.observationCentroids,
    data.severityAreas,
    data.temporalChanges,
    data.interventionZones,
  ].flatMap((collection) =>
    collection.features.flatMap((feature) =>
      positions("coordinates" in feature.geometry ? feature.geometry.coordinates : []),
    ),
  );
}
