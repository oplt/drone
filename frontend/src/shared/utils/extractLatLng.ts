export type LatLng = { lat: number; lng: number };

type LatLngSource = {
  lat?: unknown;
  latitude?: unknown;
  Lat?: unknown;
  Latitude?: unknown;
  lon?: unknown;
  lng?: unknown;
  longitude?: unknown;
  Lon?: unknown;
  Lng?: unknown;
  Longitude?: unknown;
  coordinates?: unknown;
  coords?: unknown;
  position?: LatLngSource;
  location?: LatLngSource;
  global_position?: LatLngSource;
  globalPosition?: LatLngSource;
  global_frame?: LatLngSource;
  globalFrame?: LatLngSource;
  payload?: LatLngSource;
  data?: LatLngSource;
  telemetry?: LatLngSource;
  runtime_metrics?: LatLngSource;
  vehicle?: LatLngSource;
  drone?: LatLngSource;
};

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readLatLng(value: LatLngSource): LatLng | null {
  const lat = toFiniteNumber(
    value.lat ?? value.latitude ?? value.Lat ?? value.Latitude,
  );
  const lon = toFiniteNumber(
    value.lon ??
      value.lng ??
      value.longitude ??
      value.Lon ??
      value.Lng ??
      value.Longitude,
  );

  if (lat === null || lon === null) return null;
  if (lat < -90 || lat > 90) return null;
  if (lon < -180 || lon > 180) return null;
  if (Math.abs(lat) < 1e-8 && Math.abs(lon) < 1e-8) return null;

  return { lat, lng: lon };
}

function readCoordinateArray(value: unknown): LatLng | null {
  if (!Array.isArray(value) || value.length < 2) return null;

  const first = toFiniteNumber(value[0]);
  const second = toFiniteNumber(value[1]);
  if (first === null || second === null) return null;

  const lonLat =
    first >= -180 && first <= 180 && second >= -90 && second <= 90
      ? { lat: second, lng: first }
      : null;
  const latLng =
    first >= -90 && first <= 90 && second >= -180 && second <= 180
      ? { lat: first, lng: second }
      : null;

  const result = lonLat ?? latLng;
  if (!result) return null;
  if (Math.abs(result.lat) < 1e-8 && Math.abs(result.lng) < 1e-8) return null;
  return result;
}

export function extractLatLng(value: unknown): LatLng | null {
  if (!value || typeof value !== "object") return null;
  const source = value as LatLngSource;

  return (
    readLatLng(source) ??
    readCoordinateArray(source.coordinates) ??
    readCoordinateArray(source.coords) ??
    (source.position ? readLatLng(source.position) : null) ??
    (source.position ? readCoordinateArray(source.position.coordinates) : null) ??
    (source.location ? extractLatLng(source.location) : null) ??
    (source.global_position ? extractLatLng(source.global_position) : null) ??
    (source.globalPosition ? extractLatLng(source.globalPosition) : null) ??
    (source.global_frame ? extractLatLng(source.global_frame) : null) ??
    (source.globalFrame ? extractLatLng(source.globalFrame) : null) ??
    (source.payload ? extractLatLng(source.payload) : null) ??
    (source.data ? extractLatLng(source.data) : null) ??
    (source.telemetry ? extractLatLng(source.telemetry) : null) ??
    (source.runtime_metrics ? extractLatLng(source.runtime_metrics) : null) ??
    (source.vehicle ? extractLatLng(source.vehicle) : null) ??
    (source.drone ? extractLatLng(source.drone) : null)
  );
}
