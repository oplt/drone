import { useEffect } from "react";
import type { DrawMode, MissionMapEngine, TerraDrawEditorMode } from "../types";

const DRAW_MODE_TO_TERRA_DRAW_MODE: Partial<Record<DrawMode, TerraDrawEditorMode>> = {
  polygon: "polygon",
  polyline: "linestring",
  point: "point",
  rectangle: "rectangle",
  circle: "circle",
  freehand: "freehand",
  triangle: "polygon",
  none: "static",
};

export function useSyncTerraDrawMode({
  drawMode,
  mapEngine,
  setTerraDrawMode,
}: {
  drawMode: DrawMode;
  mapEngine: MissionMapEngine;
  setTerraDrawMode: (mode: TerraDrawEditorMode) => void;
}) {
  useEffect(() => {
    if (mapEngine !== "google") return;

    const terraDrawMode = DRAW_MODE_TO_TERRA_DRAW_MODE[drawMode];
    if (terraDrawMode) setTerraDrawMode(terraDrawMode);
  }, [drawMode, mapEngine, setTerraDrawMode]);
}
