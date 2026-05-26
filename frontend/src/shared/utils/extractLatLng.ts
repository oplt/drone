export type LatLng = { lat: number; lng: number };

export function extractLatLng(value: any): LatLng | null {
  if (!value) return null;

  const lat =
    value.lat ??
    value.latitude ??
    value.Lat ??
    value.Latitude ??
    (value.position ? value.position.lat ?? value.position.latitude : undefined);

  const lon =
    value.lon ??
    value.lng ??
    value.longitude ??
    value.Lon ??
    value.Lng ??
    value.Longitude ??
    (value.position
      ? value.position.lon ?? value.position.lng ?? value.position.longitude
      : undefined);

  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90) return null;
  if (lon < -180 || lon > 180) return null;

  return { lat, lng: lon };
}
