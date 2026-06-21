import type { FieldFeature, LatLng, LonLat } from "../types";

export function lonLatRingToPath(ring: LonLat[]): LatLng[] {
  return ring.map(([lon, lat]) => ({ lat, lng: lon }));
}

export function stripClosedRing(ring: LonLat[]): LonLat[] {
  if (ring.length >= 2) {
    const a = ring[0];
    const b = ring[ring.length - 1];
    if (a[0] === b[0] && a[1] === b[1]) return ring.slice(0, -1);
  }
  return ring;
}

export function computeCentroid(ring: LonLat[]): LatLng | null {
  const pts = stripClosedRing(ring);
  if (pts.length < 3) return null;

  let twiceArea = 0;
  let cx = 0;
  let cy = 0;

  for (let i = 0; i < pts.length; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[(i + 1) % pts.length];
    const f = x0 * y1 - x1 * y0;
    twiceArea += f;
    cx += (x0 + x1) * f;
    cy += (y0 + y1) * f;
  }

  if (Math.abs(twiceArea) < 1e-12) {
    const avg = pts.reduce((acc, [x, y]) => ({ x: acc.x + x, y: acc.y + y }), { x: 0, y: 0 });
    return { lng: avg.x / pts.length, lat: avg.y / pts.length };
  }

  const area6 = twiceArea * 3;
  return { lng: cx / area6, lat: cy / area6 };
}

export function computeRingMapViewport(
  ring: LonLat[],
): { center: LatLng; zoom: number } | null {
  const pts = stripClosedRing(ring);
  if (pts.length < 3) return null;

  const center = computeCentroid(ring);
  if (!center) return null;

  let west = Infinity;
  let east = -Infinity;
  let south = Infinity;
  let north = -Infinity;

  for (const [lon, lat] of pts) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }

  const latSpan = Math.max(0, north - south);
  const lngScale = Math.max(0.2, Math.cos((center.lat * Math.PI) / 180));
  const lngSpan = Math.max(0, east - west) * lngScale;
  const maxSpan = Math.max(latSpan, lngSpan, 0.0005);
  const zoom = Math.max(
    3,
    Math.min(20, Math.floor(Math.log2(360 / (maxSpan * 1.45)))),
  );

  return { center, zoom };
}

export function ringLatLngBounds(
  ring: LonLat[],
): { south: number; west: number; north: number; east: number } | null {
  const pts = stripClosedRing(ring);
  if (pts.length < 3) return null;

  let west = Infinity;
  let east = -Infinity;
  let south = Infinity;
  let north = -Infinity;

  for (const [lon, lat] of pts) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }

  if (!Number.isFinite(west) || !Number.isFinite(east)) return null;
  return { south, west, north, east };
}

export function computeAreaHa(ring: LonLat[]): number | null {
  const pts = stripClosedRing(ring);
  if (pts.length < 3) return null;
  const gmaps = (window as typeof window & { google?: typeof google }).google;
  if (!gmaps?.maps?.geometry?.spherical) return null;
  const latLngs = pts.map(([lon, lat]) => new gmaps.maps.LatLng(lat, lon));
  const m2 = gmaps.maps.geometry.spherical.computeArea(latLngs);
  return m2 / 10000;
}

export function parseFieldFeatures(fc: {
  features?: Array<{
    properties?: Record<string, unknown>;
    geometry?: { coordinates?: LonLat[][] };
  }>;
}): FieldFeature[] {
  const features: FieldFeature[] = [];

  for (const feat of fc.features ?? []) {
    const props = feat.properties ?? {};
    const coords = feat.geometry?.coordinates?.[0];
    if (!coords || coords.length < 4) continue;
    const ring = stripClosedRing(coords);
    features.push({
      id: Number(props.id),
      owner_id: props.owner_id != null ? Number(props.owner_id) : undefined,
      name: String(props.name ?? ""),
      area_ha: props.area_ha != null ? Number(props.area_ha) : null,
      ring,
      path: lonLatRingToPath(ring),
    });
  }

  return features.sort((a, b) => b.id - a.id);
}
