import { useCallback } from "react";
import { syncMapLibreDrawPreview } from "../adapters/maplibre/maplibreDrawPreview";
import type { FlatDrawMode, LonLat } from "../adapters/maplibre/maplibreMapTypes";
import { isNearLonLat, isNearLonLatPixels } from "../utils/flatMapShapeGeometry";
import { useFlatMapDrawing } from "./useFlatMapDrawing";
import type { MapLibreMapRefs } from "./useMapLibreMapRefs";

type UseMapLibreDrawingArgs = {
  refs: MapLibreMapRefs;
  drawMode: FlatDrawMode;
  onDrawComplete?: (result: import("../adapters/maplibre/maplibreMapTypes").FlatDrawResult) => void;
  onPickLatLng?: (p: { lat: number; lng: number }) => void;
  onBoundaryDrawStarted?: () => void;
  onBoundaryDrawProgress?: (coords: LonLat[]) => void;
};

export function useMapLibreDrawing({
  refs,
  drawMode,
  onDrawComplete,
  onPickLatLng,
  onBoundaryDrawStarted,
  onBoundaryDrawProgress,
}: UseMapLibreDrawingArgs) {
  const setDrawingModeState = useCallback(
    (mode: FlatDrawMode) => {
      if (!refs.mapRef.current) return;
      if (mode === "none") refs.mapRef.current.doubleClickZoom.enable();
      else refs.mapRef.current.doubleClickZoom.disable();
    },
    [refs],
  );

  const isNearCoord = useCallback(
    (a: LonLat, b: LonLat) => {
      const map = refs.mapRef.current;
      if (map) {
        return isNearLonLatPixels(map, a, b) || isNearLonLat(a, b);
      }
      return isNearLonLat(a, b);
    },
    [refs],
  );

  const updateDrawingPreview = useCallback(
    (mode: FlatDrawMode, coords: LonLat[]) => {
      const map = refs.mapRef.current;
      if (!map) return;
      syncMapLibreDrawPreview(map, mode, coords);
    },
    [refs],
  );

  const drawing = useFlatMapDrawing({
    drawMode,
    onDrawComplete,
    onPickLatLng,
    onPreview: updateDrawingPreview,
    onModeStateChange: setDrawingModeState,
    onBoundaryDrawStarted,
    onBoundaryDrawProgress,
    isNearCoord,
  });

  refs.drawingRef.current = drawing;

  return drawing;
}
