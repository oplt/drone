import { stripClosedRing, type LonLat } from "../../fields";
import type { ShapeDrawResult } from "./drawingShapes";

export function ringFromFlatDrawResult(result: ShapeDrawResult): LonLat[] | null {
  if (result.type === "point") return null;

  const ring = stripClosedRing(
    result.coordinates.map(([lon, lat]) => [lon, lat] as LonLat),
  );

  return ring.length >= 3 ? ring : null;
}
