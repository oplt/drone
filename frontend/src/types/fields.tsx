// GeoJSON order ALWAYS: [lon, lat]
export type LonLat = [number, number];

export interface FieldCreateDTO {
  name: string;
  coordinates: LonLat[];      // ring (open ok); backend closes
  owner_id?: number | null;
  metadata?: Record<string, unknown>;
}

export interface FieldOutDTO {
  id: number;
  owner_id?: number | null;
  name: string;
  area_ha?: number | null;
  metadata: Record<string, unknown>;
}

// Google Maps uses {lat,lng}; convert at boundaries
export type LatLng = { lat: number; lng: number };

export function gmapsPathToLonLat(path: LatLng[]): LonLat[] {
  return path.map(p => [p.lng, p.lat]);
}

export function lonLatToGmapsPath(ring: LonLat[]): LatLng[] {
  return ring.map(([lon, lat]) => ({ lat, lng: lon }));
}