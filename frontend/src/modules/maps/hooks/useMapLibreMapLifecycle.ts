import { useEffect } from "react";
import {
  bootstrapMapLibre,
  teardownMapLibre,
} from "../adapters/maplibre/maplibreMapBootstrap";
import type { LatLng } from "../adapters/maplibre/maplibreMapTypes";
import type { MapLibreMapRefs } from "./useMapLibreMapRefs";

type UseMapLibreMapLifecycleArgs = {
  refs: MapLibreMapRefs;
  center: LatLng;
  zoom: number;
};

export function useMapLibreMapLifecycle({
  refs,
  center,
  zoom,
}: UseMapLibreMapLifecycleArgs) {
  useEffect(() => {
    if (!refs.hostRef.current || refs.mapRef.current) return;

    refs.mapRef.current = bootstrapMapLibre({
      hostElement: refs.hostRef.current,
      center,
      zoom,
      refs: {
        mapRef: refs.mapRef,
        drawModeRef: refs.drawModeRef,
        drawingRef: refs.drawingRef,
        onSavedFieldClickRef: refs.onSavedFieldClickRef,
        onFieldBoundaryClickRef: refs.onFieldBoundaryClickRef,
        waypointMarkersRef: refs.waypointMarkersRef,
        droneMarkerRef: refs.droneMarkerRef,
        userMarkerRef: refs.userMarkerRef,
      },
    });

    return () => {
      teardownMapLibre({
        mapRef: refs.mapRef,
        drawModeRef: refs.drawModeRef,
        drawingRef: refs.drawingRef,
        onSavedFieldClickRef: refs.onSavedFieldClickRef,
        onFieldBoundaryClickRef: refs.onFieldBoundaryClickRef,
        waypointMarkersRef: refs.waypointMarkersRef,
        droneMarkerRef: refs.droneMarkerRef,
        userMarkerRef: refs.userMarkerRef,
      });
    };
    // Map is created once; center/zoom updates are handled by useMapLibreCamera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
