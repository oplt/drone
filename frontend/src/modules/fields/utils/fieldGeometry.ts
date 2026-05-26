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
