import type { LonLat } from "./drawingShapes";
import type { ShapeDrawMode } from "./drawingShapes";
import { shouldCloseShapeOnClick } from "./flatMapShapeGeometry";

type NearCoordFn = (a: LonLat, b: LonLat) => boolean;

/** Handles a click while drawing on Leaflet / MapLibre. Returns the updated in-progress coords. */
export function handleFlatMapShapeClick(
  mode: ShapeDrawMode,
  coord: LonLat,
  drawing: LonLat[],
  onPreview: (coords: LonLat[]) => void,
  onFinish: (coords: LonLat[]) => void,
  isNearCoord?: NearCoordFn,
): LonLat[] {
  if (mode === "rectangle" || mode === "circle" || mode === "triangle") {
    if (drawing.length === 0) {
      const next = [coord];
      onPreview(next);
      return next;
    }
    const next = [drawing[0], coord];
    onPreview(next);
    onFinish(next);
    return [];
  }

  if (mode === "freehand") {
    return drawing;
  }

  if (shouldCloseShapeOnClick(mode, drawing, coord, isNearCoord)) {
    onFinish(drawing);
    return [];
  }

  const next = [...drawing, coord];
  onPreview(next);
  return next;
}
