export type LonLat = [number, number];
export type ShapeDrawMode =
  | "none"
  | "point"
  | "polyline"
  | "polygon"
  | "rectangle"
  | "circle"
  | "freehand"
  | "triangle";

export type ShapeDrawResult =
  | { type: "point"; coordinates: LonLat }
  | { type: "polyline"; coordinates: LonLat[] }
  | { type: "polygon"; coordinates: LonLat[] };

export function rectangleRing(start: LonLat, end: LonLat): LonLat[] {
  return [
    start,
    [end[0], start[1]],
    end,
    [start[0], end[1]],
  ];
}

export function triangleRing(start: LonLat, end: LonLat): LonLat[] {
  const halfWidth = Math.abs(end[0] - start[0]);
  const apex: LonLat = [start[0], start[1]];
  const baseY = end[1];
  return [
    apex,
    [start[0] + halfWidth, baseY],
    [start[0] - halfWidth, baseY],
  ];
}

export function circleRing(center: LonLat, edge: LonLat, steps = 64): LonLat[] {
  const latScale = Math.max(0.2, Math.cos((center[1] * Math.PI) / 180));
  const dx = (edge[0] - center[0]) * latScale;
  const dy = edge[1] - center[1];
  const radius = Math.sqrt(dx * dx + dy * dy);
  if (radius <= 0) return [];

  return Array.from({ length: steps }, (_, index) => {
    const angle = (index / steps) * Math.PI * 2;
    return [
      center[0] + (Math.cos(angle) * radius) / latScale,
      center[1] + Math.sin(angle) * radius,
    ] as LonLat;
  });
}

export function closeRing(coords: LonLat[]): LonLat[] {
  if (coords.length === 0) return coords;
  const first = coords[0];
  const last = coords[coords.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return coords;
  return [...coords, first];
}

export function shapePreview(mode: ShapeDrawMode, coords: LonLat[]): LonLat[] {
  if (mode === "rectangle" && coords.length >= 2) return rectangleRing(coords[0], coords[coords.length - 1]);
  if (mode === "circle" && coords.length >= 2) return circleRing(coords[0], coords[coords.length - 1]);
  if (mode === "triangle" && coords.length >= 2) return triangleRing(coords[0], coords[coords.length - 1]);
  return coords;
}

export function moveTwoCornerShapePreview(
  mode: ShapeDrawMode,
  coords: LonLat[],
  cursor: LonLat,
): LonLat[] | null {
  if (!["rectangle", "circle", "triangle"].includes(mode) || coords.length === 0) {
    return null;
  }

  return [coords[0], cursor];
}

export function completeShape(mode: ShapeDrawMode, coords: LonLat[]): ShapeDrawResult | null {
  if (mode === "point" && coords.length >= 1) {
    return { type: "point", coordinates: coords[0] };
  }
  if (mode === "polyline" && coords.length >= 2) {
    return { type: "polyline", coordinates: coords };
  }
  if (mode === "polygon" && coords.length >= 3) {
    return { type: "polygon", coordinates: coords };
  }
  if (mode === "rectangle" && coords.length >= 2) {
    return { type: "polygon", coordinates: rectangleRing(coords[0], coords[coords.length - 1]) };
  }
  if (mode === "circle" && coords.length >= 2) {
    const ring = circleRing(coords[0], coords[coords.length - 1]);
    return ring.length >= 3 ? { type: "polygon", coordinates: ring } : null;
  }
  if (mode === "triangle" && coords.length >= 2) {
    return { type: "polygon", coordinates: triangleRing(coords[0], coords[coords.length - 1]) };
  }
  if (mode === "freehand" && coords.length >= 3) {
    return { type: "polygon", coordinates: coords };
  }
  return null;
}
