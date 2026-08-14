import type { Map as MapLibreMapInstance } from "maplibre-gl";
import maplibregl from "maplibre-gl";
import type { MutableRefObject } from "react";
import type { useFlatMapDrawing } from "../../hooks/useFlatMapDrawing";
import {
  overlayFillLayerId,
  type FlatDrawMode,
  type LatLng,
} from "./maplibreMapTypes";
import { clearMapLibreDrawPreview } from "./maplibreDrawPreview";

export type MapLibreBootstrapRefs = {
  mapRef: MutableRefObject<MapLibreMapInstance | null>;
  drawModeRef: MutableRefObject<FlatDrawMode>;
  drawingRef: MutableRefObject<ReturnType<typeof useFlatMapDrawing> | null>;
  onSavedFieldClickRef: MutableRefObject<((fieldId: number) => void) | undefined>;
  onFieldBoundaryClickRef: MutableRefObject<(() => void) | undefined>;
  waypointMarkersRef: MutableRefObject<maplibregl.Marker[]>;
  droneMarkerRef: MutableRefObject<maplibregl.Marker | null>;
  userMarkerRef: MutableRefObject<maplibregl.Marker | null>;
};

export type MapLibreBootstrapArgs = {
  hostElement: HTMLDivElement;
  center: LatLng;
  zoom: number;
  refs: MapLibreBootstrapRefs;
};

export function bootstrapMapLibre({
  hostElement,
  center,
  zoom,
  refs,
}: MapLibreBootstrapArgs): MapLibreMapInstance {
  const map = new maplibregl.Map({
    container: hostElement,
    center: [center.lng, center.lat],
    zoom,
    style: "https://tiles.stadiamaps.com/styles/alidade_smooth.json",
  });

  map.addControl(
    new maplibregl.NavigationControl({ visualizePitch: true }),
    "top-right",
  );
  map.once("load", () => {
    setTimeout(() => map.resize(), 0);
    clearMapLibreDrawPreview(map);
  });
  map.on("click", (event: maplibregl.MapMouseEvent) => {
    if (refs.drawModeRef.current !== "none") {
      refs.drawingRef.current?.handleClick([event.lngLat.lng, event.lngLat.lat]);
      return;
    }

    if (map.getLayer(overlayFillLayerId)) {
      const overlayFeatures = map.queryRenderedFeatures(event.point, {
        layers: [overlayFillLayerId],
      });
      const savedField = overlayFeatures.find(
        (item) => item.properties?.kind === "saved-field",
      );
      if (savedField) {
        const fieldId = savedField.properties?.fieldId;
        if (typeof fieldId === "number") {
          refs.onSavedFieldClickRef.current?.(fieldId);
          return;
        }
        if (typeof fieldId === "string") {
          refs.onSavedFieldClickRef.current?.(Number(fieldId));
          return;
        }
      }
      const drawnBoundary = overlayFeatures.find(
        (item) => item.properties?.kind === "field",
      );
      if (drawnBoundary) {
        refs.onFieldBoundaryClickRef.current?.();
        return;
      }
    }
    refs.drawingRef.current?.handleClick([event.lngLat.lng, event.lngLat.lat]);
  });
  map.on("mousedown", (event: maplibregl.MapMouseEvent) => {
    if (
      refs.drawingRef.current?.startFreehand([event.lngLat.lng, event.lngLat.lat])
    ) {
      map.dragPan.disable();
    }
  });
  map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
    refs.drawingRef.current?.movePointer([event.lngLat.lng, event.lngLat.lat]);
  });
  map.on("mouseup", () => {
    if (refs.drawingRef.current?.endFreehand()) map.dragPan.enable();
  });
  map.on("dblclick", (event) => {
    event.preventDefault();
    if (refs.drawModeRef.current !== "none") {
      refs.drawingRef.current?.finishDrawing();
    }
  });
  map.on("contextmenu", (event) => {
    event.preventDefault();
    if (refs.drawModeRef.current !== "none") {
      refs.drawingRef.current?.finishDrawing();
    }
  });
  map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
    if (!map.getLayer(overlayFillLayerId)) return;
    const hasSavedField = map
      .queryRenderedFeatures(event.point, { layers: [overlayFillLayerId] })
      .some((item) => item.properties?.kind === "saved-field");
    map.getCanvas().style.cursor = hasSavedField ? "pointer" : "";
  });

  return map;
}

export function teardownMapLibre(refs: MapLibreBootstrapRefs) {
  refs.waypointMarkersRef.current.forEach((marker) => marker.remove());
  refs.waypointMarkersRef.current = [];
  refs.droneMarkerRef.current?.remove();
  refs.droneMarkerRef.current = null;
  refs.userMarkerRef.current?.remove();
  refs.userMarkerRef.current = null;
  refs.mapRef.current?.remove();
  refs.mapRef.current = null;
}
