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
  position?: LatLngSource;
  payload?: LatLngSource;
  data?: LatLngSource;
  telemetry?: LatLngSource;
  runtime_metrics?: LatLngSource;
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

export function extractLatLng(value: unknown): LatLng | null {
  if (!value || typeof value !== "object") return null;
  const source = value as LatLngSource;

  return (
    readLatLng(source) ??
    (source.position ? readLatLng(source.position) : null) ??
    (source.payload ? extractLatLng(source.payload) : null) ??
    (source.data ? extractLatLng(source.data) : null) ??
    (source.telemetry ? extractLatLng(source.telemetry) : null) ??
    (source.runtime_metrics ? extractLatLng(source.runtime_metrics) : null)
  );
}
