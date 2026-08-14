import type { AgricultureLonLat } from "./geometry";

export function editableZoneRing(geometry: Record<string, unknown>): AgricultureLonLat[] | null {
  if (geometry.type !== "Polygon" || !Array.isArray(geometry.coordinates)) return null;
  const ring = geometry.coordinates[0];
  if (!Array.isArray(ring)) return null;
  const points = ring.filter(
    (point): point is AgricultureLonLat =>
      Array.isArray(point) &&
      point.length >= 2 &&
      typeof point[0] === "number" &&
      typeof point[1] === "number",
  );
  return points.length >= 4 ? points : null;
}

export function ringZoneGeometry(ring: AgricultureLonLat[]): Record<string, unknown> {
  if (ring.length < 3) return {};
  const first = ring[0];
  const last = ring[ring.length - 1];
  const closed = first[0] === last[0] && first[1] === last[1] ? ring : [...ring, first];
  return { type: "Polygon", coordinates: [closed] };
}
