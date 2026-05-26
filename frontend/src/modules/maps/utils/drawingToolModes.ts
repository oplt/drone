import type { ShapeDrawMode } from "./drawingShapes";
import type { TerraDrawToolMode } from "../components/TerraDrawController";

/** Maps TerraDraw toolbar modes to flat-map (Cesium / Leaflet / MapLibre) draw modes. */
export function terraDrawToolToShapeMode(tool: TerraDrawToolMode): ShapeDrawMode {
  const modeMap: Record<TerraDrawToolMode, ShapeDrawMode> = {
    polygon: "polygon",
    linestring: "polyline",
    point: "point",
    rectangle: "rectangle",
    circle: "circle",
    freehand: "freehand",
    select: "none",
  };
  return modeMap[tool] ?? "none";
}

export function isFlatDrawToolSelected(
  drawMode: ShapeDrawMode,
  tool: TerraDrawToolMode,
): boolean {
  if (tool === "select") return drawMode === "none";
  if (tool === "linestring") return drawMode === "polyline";
  if (tool === "polygon") return drawMode === "polygon";
  if (tool === "rectangle") return drawMode === "rectangle";
  if (tool === "circle") return drawMode === "circle";
  if (tool === "freehand") return drawMode === "freehand";
  if (tool === "point") return drawMode === "point";
  return false;
}
