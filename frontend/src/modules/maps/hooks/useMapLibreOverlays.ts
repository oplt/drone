import { useEffect } from "react";
import { syncMapLibreOverlays } from "../adapters/maplibre/maplibreOverlays";
import type {
  FlatDrawMode,
  LonLat,
  SavedFieldBoundary,
} from "../adapters/maplibre/maplibreMapTypes";
import type { MapLibreMapRefs } from "./useMapLibreMapRefs";

type UseMapLibreOverlaysArgs = {
  refs: MapLibreMapRefs;
  drawMode: FlatDrawMode;
  savedFields: SavedFieldBoundary[];
  selectedFieldId: number | null;
  fieldBoundary: LonLat[] | null;
  drawnBoundarySelected: boolean;
  exclusionZones: LonLat[][];
  plannedRoute: LonLat[] | null;
};

export function useMapLibreOverlays({
  refs,
  drawMode,
  savedFields,
  selectedFieldId,
  fieldBoundary,
  drawnBoundarySelected,
  exclusionZones,
  plannedRoute,
}: UseMapLibreOverlaysArgs) {
  useEffect(() => {
    const map = refs.mapRef.current;
    if (!map) return;

    const updateOverlays = () => {
      syncMapLibreOverlays(map, {
        drawMode,
        savedFields,
        selectedFieldId,
        fieldBoundary,
        drawnBoundarySelected,
        exclusionZones,
        plannedRoute,
      });
    };

    if (map.loaded()) updateOverlays();
    else map.once("load", updateOverlays);
  }, [
    refs,
    drawMode,
    exclusionZones,
    fieldBoundary,
    plannedRoute,
    savedFields,
    selectedFieldId,
    drawnBoundarySelected,
  ]);
}
