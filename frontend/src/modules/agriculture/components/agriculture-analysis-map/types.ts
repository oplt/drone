import type { Feature, FeatureCollection, Geometry } from "geojson";

export type AgricultureMapFeature = Feature<
  Geometry,
  Record<string, unknown>
>;

export type AgricultureMapFeatureCollection = FeatureCollection<
  Geometry,
  Record<string, unknown>
>;

export type AgricultureMapGeoJson = {
  type?: string;
  features?: Array<Record<string, unknown>>;
};

export type AgricultureMapLayerKey =
  | "fieldBoundary"
  | "flightPath"
  | "observations"
  | "severity"
  | "heatmap"
  | "temporalChanges"
  | "interventionZones";

export type AgricultureMapLayerVisibility = Record<
  AgricultureMapLayerKey,
  boolean
>;

export type AgricultureMapContextStatus = {
  fieldBoundary: "available" | "loading" | "unavailable";
  flightPath: "available" | "loading" | "unavailable" | "partial";
};

export type AgricultureAnalysisMapProps = {
  observations: AgricultureMapGeoJson;
  fieldBoundary?: AgricultureMapGeoJson | null;
  flightPath?: AgricultureMapGeoJson | null;
  severityAreas?: AgricultureMapGeoJson | null;
  interventionZones?: AgricultureMapGeoJson | null;
  temporalChanges?: AgricultureMapGeoJson | null;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  initialVisibility?: Partial<AgricultureMapLayerVisibility>;
  contextStatus?: AgricultureMapContextStatus;
  height?: number;
};

export type AgricultureMapData = {
  fieldBoundary: AgricultureMapFeatureCollection;
  flightPath: AgricultureMapFeatureCollection;
  observationCentroids: AgricultureMapFeatureCollection;
  observationShapes: AgricultureMapFeatureCollection;
  severityAreas: AgricultureMapFeatureCollection;
  interventionZones: AgricultureMapFeatureCollection;
  temporalChanges: AgricultureMapFeatureCollection;
  selection: AgricultureMapFeatureCollection;
};

export type AgricultureAccessibleFeature = {
  id: string;
  label: string;
  severity: number;
};
