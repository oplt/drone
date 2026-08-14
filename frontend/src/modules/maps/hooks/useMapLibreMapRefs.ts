import { useEffect, useRef } from "react";
import type { Map as MapLibreMapInstance, Marker } from "maplibre-gl";
import type { useFlatMapDrawing } from "./useFlatMapDrawing";
import type {
  FlatDrawMode,
  MapLibreMapProps,
} from "../adapters/maplibre/maplibreMapTypes";

export function useMapLibreMapRefs(props: MapLibreMapProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMapInstance | null>(null);
  const waypointMarkersRef = useRef<Marker[]>([]);
  const droneMarkerRef = useRef<Marker | null>(null);
  const userMarkerRef = useRef<Marker | null>(null);
  const drawingRef = useRef<ReturnType<typeof useFlatMapDrawing> | null>(null);
  const onSavedFieldClickRef = useRef<MapLibreMapProps["onSavedFieldClick"]>(
    props.onSavedFieldClick,
  );
  const onFieldBoundaryClickRef = useRef<MapLibreMapProps["onFieldBoundaryClick"]>(
    props.onFieldBoundaryClick,
  );
  const drawModeRef = useRef<FlatDrawMode>(props.drawMode ?? "none");

  useEffect(() => {
    onSavedFieldClickRef.current = props.onSavedFieldClick;
  }, [props.onSavedFieldClick]);
  useEffect(() => {
    onFieldBoundaryClickRef.current = props.onFieldBoundaryClick;
  }, [props.onFieldBoundaryClick]);
  useEffect(() => {
    drawModeRef.current = props.drawMode ?? "none";
  }, [props.drawMode]);

  return {
    hostRef,
    mapRef,
    waypointMarkersRef,
    droneMarkerRef,
    userMarkerRef,
    drawingRef,
    onSavedFieldClickRef,
    onFieldBoundaryClickRef,
    drawModeRef,
  };
}

export type MapLibreMapRefs = ReturnType<typeof useMapLibreMapRefs>;
