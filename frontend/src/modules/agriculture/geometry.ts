export type AgricultureLonLat = [number, number];
export type AgriculturePolygon = {
  type: "Polygon";
  coordinates: AgricultureLonLat[][];
};

const orientation = (a: AgricultureLonLat, b: AgricultureLonLat, c: AgricultureLonLat) =>
  Math.sign((b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1]));

function segmentsIntersect(
  a: AgricultureLonLat,
  b: AgricultureLonLat,
  c: AgricultureLonLat,
  d: AgricultureLonLat,
) {
  return orientation(a, b, c) !== orientation(a, b, d) &&
    orientation(c, d, a) !== orientation(c, d, b);
}

export function validateAgriculturePolygon(value: unknown): AgriculturePolygon {
  const candidate =
    value && typeof value === "object" && "geometry" in value
      ? (value as { geometry?: unknown }).geometry
      : value;
  if (!candidate || typeof candidate !== "object") {
    throw new Error("Draw or import a field boundary.");
  }
  const geometry = candidate as Partial<AgriculturePolygon>;
  if (geometry.type !== "Polygon" || !Array.isArray(geometry.coordinates)) {
    throw new Error("Boundary must be a GeoJSON Polygon.");
  }
  const rawRing = geometry.coordinates[0];
  if (!Array.isArray(rawRing) || rawRing.length < 3) {
    throw new Error("Boundary needs at least three points.");
  }
  const ring = rawRing.map((point) => {
    if (
      !Array.isArray(point) ||
      point.length < 2 ||
      !Number.isFinite(point[0]) ||
      !Number.isFinite(point[1]) ||
      Math.abs(point[0]) > 180 ||
      Math.abs(point[1]) > 90
    ) {
      throw new Error("Boundary coordinates must be valid longitude and latitude values.");
    }
    return [Number(point[0]), Number(point[1])] as AgricultureLonLat;
  });
  const first = ring[0];
  const last = ring[ring.length - 1];
  const closed =
    first[0] === last[0] && first[1] === last[1] ? ring : [...ring, first];
  for (let left = 0; left < closed.length - 1; left += 1) {
    for (let right = left + 2; right < closed.length - 1; right += 1) {
      if (left === 0 && right === closed.length - 2) continue;
      if (segmentsIntersect(closed[left], closed[left + 1], closed[right], closed[right + 1])) {
        throw new Error("Boundary crosses itself. Move or remove the intersecting points.");
      }
    }
  }
  return { type: "Polygon", coordinates: [closed] };
}

export function polygonRing(polygon: AgriculturePolygon | null): AgricultureLonLat[] | null {
  if (!polygon) return null;
  const ring = polygon.coordinates[0] ?? [];
  if (ring.length > 1 && ring[0][0] === ring.at(-1)?.[0] && ring[0][1] === ring.at(-1)?.[1]) {
    return ring.slice(0, -1);
  }
  return ring;
}
