import { useCallback, useRef, useState } from "react";
import type { TerraDraw } from "terra-draw";
import type { RouteDrawMode, RouteDrawToolMode, TerraDrawEditorMode } from "../../maps";
import type { LatLng } from "../../../shared/utils/extractLatLng";

const GOOGLE_TERRA_DRAW_MODE: Record<RouteDrawToolMode, TerraDrawEditorMode> = {
  none: "select",
  point: "point",
  polyline: "linestring",
  polygon: "polygon",
  rectangle: "rectangle",
  circle: "circle",
  triangle: "polygon",
};

export function useControlledFlightRouteDrawing() {
  const terraDrawRef = useRef<TerraDraw | null>(null);
  const [drawMode, setDrawMode] = useState<RouteDrawMode>("point");
  const [terraDrawMode, setTerraDrawMode] = useState<TerraDrawEditorMode>("point");
  const [, setTerraDrawReady] = useState(false);
  const [drawnPoints, setDrawnPoints] = useState<LatLng[]>([]);

  const onMapClick = useCallback(
    (event: google.maps.MapMouseEvent) => {
      if (terraDrawMode !== "static" && terraDrawMode !== "select") return;
      if (drawMode === "none" || !event.latLng) return;
      setDrawnPoints((prev) => [...prev, { lat: event.latLng!.lat(), lng: event.latLng!.lng() }]);
    },
    [drawMode, terraDrawMode],
  );

  const handleRouteToolModeChange = useCallback((toolMode: RouteDrawToolMode) => {
    setTerraDrawMode(GOOGLE_TERRA_DRAW_MODE[toolMode]);
  }, []);

  const undo = useCallback(() => {
    setDrawnPoints((prev) => prev.slice(0, -1));
  }, []);

  return {
    terraDrawRef,
    drawMode,
    setDrawMode,
    terraDrawMode,
    setTerraDrawReady,
    drawnPoints,
    onMapClick,
    handleRouteToolModeChange,
    undo,
  };
}
