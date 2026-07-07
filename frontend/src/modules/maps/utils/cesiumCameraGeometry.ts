export type CameraLatLng = { lat: number; lng: number };
export type CameraLonLat = [number, number];

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

export function zoomToHeightMeters(zoom: number): number {
  const normalizedZoom = clamp(zoom, 1, 20);
  return Math.round(20_000_000 / Math.pow(2, normalizedZoom));
}

export function normalizeLonLatLine(
  coordinates: CameraLonLat[] | null | undefined,
): CameraLonLat[] {
  if (!coordinates?.length) return [];
  return coordinates.filter(
    (coordinate) =>
      Array.isArray(coordinate) &&
      coordinate.length >= 2 &&
      Number.isFinite(coordinate[0]) &&
      Number.isFinite(coordinate[1]),
  );
}

export function normalizeLonLatRing(
  coordinates: CameraLonLat[] | null | undefined,
): CameraLonLat[] {
  const line = normalizeLonLatLine(coordinates);
  if (line.length < 3) return [];
  const first = line[0];
  const last = line[line.length - 1];
  return first[0] === last[0] && first[1] === last[1] ? line.slice(0, -1) : line;
}

export function computeRingCentroid(
  coordinates: CameraLonLat[] | null | undefined,
): CameraLatLng | null {
  const ring = normalizeLonLatRing(coordinates);
  if (ring.length < 3) return null;

  let twiceArea = 0;
  let longitudeTotal = 0;
  let latitudeTotal = 0;

  for (let index = 0; index < ring.length; index += 1) {
    const [longitudeA, latitudeA] = ring[index];
    const [longitudeB, latitudeB] = ring[(index + 1) % ring.length];
    const crossProduct = longitudeA * latitudeB - longitudeB * latitudeA;
    twiceArea += crossProduct;
    longitudeTotal += (longitudeA + longitudeB) * crossProduct;
    latitudeTotal += (latitudeA + latitudeB) * crossProduct;
  }

  if (Math.abs(twiceArea) < 1e-12) {
    const total = ring.reduce(
      (sum, [lng, lat]) => ({ lng: sum.lng + lng, lat: sum.lat + lat }),
      { lng: 0, lat: 0 },
    );
    return { lng: total.lng / ring.length, lat: total.lat / ring.length };
  }

  return {
    lng: longitudeTotal / (3 * twiceArea),
    lat: latitudeTotal / (3 * twiceArea),
  };
}

export function computeFieldCameraView(
  coordinates: CameraLonLat[] | null | undefined,
): { center: CameraLatLng; topHeight: number } | null {
  const ring = normalizeLonLatRing(coordinates);
  if (ring.length < 3) return null;
  const center = computeRingCentroid(ring);
  if (!center) return null;

  let west = Infinity;
  let east = -Infinity;
  let south = Infinity;
  let north = -Infinity;
  for (const [lng, lat] of ring) {
    west = Math.min(west, lng);
    east = Math.max(east, lng);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }

  const latitudeSpanMeters = Math.max(0, north - south) * 111_320;
  const longitudeScale = Math.max(0.2, Math.cos((center.lat * Math.PI) / 180));
  const longitudeSpanMeters = Math.max(0, east - west) * 111_320 * longitudeScale;
  const spanMeters = Math.max(latitudeSpanMeters, longitudeSpanMeters);

  return {
    center,
    topHeight: clamp(Math.round(spanMeters * 2.4), 120, 20_000),
  };
}
