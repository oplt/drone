// GeoJSON order ALWAYS: [lon, lat]
import type { FieldWorkflowScope } from "./constants";

export type LonLat = [number, number];

export interface FieldCreateDTO {
  name: string;
  coordinates: LonLat[];
  owner_id?: number | null;
  workflow_scope?: FieldWorkflowScope | null;
  metadata?: Record<string, unknown>;
}

export interface FieldOutDTO {
  id: number;
  owner_id?: number | null;
  name: string;
  area_ha?: number | null;
  workflow_scope?: FieldWorkflowScope | null;
  metadata: Record<string, unknown>;
}

export type LatLng = { lat: number; lng: number };

export function gmapsPathToLonLat(path: LatLng[]): LonLat[] {
  return path.map((p) => [p.lng, p.lat]);
}

export function lonLatToGmapsPath(ring: LonLat[]): LatLng[] {
  return ring.map(([lon, lat]) => ({ lat, lng: lon }));
}

export type FieldSummary = {
  id: number;
  owner_id?: number;
  name: string;
  area_ha?: number | null;
  workflow_scope?: FieldWorkflowScope | null;
};

export type FieldFeature = FieldSummary & {
  ring: LonLat[];
  path: LatLng[];
};

export type BorderMetrics = {
  areaHa?: number | null;
  centroid?: LatLng | null;
};

export type FieldMappingAsset = {
  type: string;
  url?: string;
};

export type FieldMappingReadyResponse = {
  assets?: FieldMappingAsset[];
};
