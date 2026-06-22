import type { LonLat, ShapeDrawMode } from "./drawingShapes";

/** ~25 m at mid-latitudes; used to close polygon/line loops on flat maps. */
export const FLAT_MAP_CLOSE_THRESHOLD_DEG = 0.00025;

export function isNearLonLat(
  a: LonLat,
  b: LonLat,
  threshold = FLAT_MAP_CLOSE_THRESHOLD_DEG,
): boolean {
  return (
    Math.abs(a[0] - b[0]) <= threshold && Math.abs(a[1] - b[1]) <= threshold
  );
}

export const FLAT_MAP_CLOSE_PIXEL_THRESHOLD = 24;

type ProjectableMap = {
  project: (lngLat: [number, number]) => { x: number; y: number };
};

export function isNearLonLatPixels(
  map: ProjectableMap,
  a: LonLat,
  b: LonLat,
  thresholdPx = FLAT_MAP_CLOSE_PIXEL_THRESHOLD,
): boolean {
  const pa = map.project(a);
  const pb = map.project(b);
  const dx = pa.x - pb.x;
  const dy = pa.y - pb.y;
  return dx * dx + dy * dy <= thresholdPx * thresholdPx;
}

export function shouldCloseShapeOnClick(
  mode: ShapeDrawMode,
  drawing: LonLat[],
  coord: LonLat,
  isNear?: (a: LonLat, b: LonLat) => boolean,
): boolean {
  if (mode !== "polygon" && mode !== "polyline") return false;
  if (drawing.length < 3) return false;
  if (isNear?.(drawing[0], coord)) return true;
  return isNearLonLat(drawing[0], coord);
}
