import { useEffect, useMemo, useRef } from "react";
import { Box, Typography } from "@mui/material";
import type { Map as MapLibreMapInstance, Marker } from "maplibre-gl";
import type { Feature, Geometry } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import maplibregl from "maplibre-gl";
import {
  closeRing,
  completeShape,
  shapePreview,
  type ShapeDrawMode,
  type ShapeDrawResult,
} from "../utils/drawingShapes";

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt?: number };
type LonLat = [number, number];
export type FlatDrawMode = ShapeDrawMode;
export type FlatDrawResult = ShapeDrawResult;

export type MapLibreMapProps = {
  center: LatLng;
  zoom: number;
  waypoints?: Waypoint[];
  droneCenter?: LatLng | null;
  userCenter?: LatLng | null;
  onPickLatLng?: (p: LatLng) => void;
  drawMode?: FlatDrawMode;
  onDrawComplete?: (result: FlatDrawResult) => void;
  fieldBoundary?: LonLat[] | null;
  plannedRoute?: LonLat[] | null;
  exclusionZones?: LonLat[][];
  height?: number | string;
};

const routeSourceId = "mission-route";
const routeLayerId = "mission-route-line";
const overlaySourceId = "mission-overlays";
const overlayFillLayerId = "mission-overlays-fill";
const overlayLineLayerId = "mission-overlays-line";
const drawSourceId = "mission-draw-preview";
const drawPointLayerId = "mission-draw-preview-points";
const drawLineLayerId = "mission-draw-preview-line";
const drawFillLayerId = "mission-draw-preview-fill";
type MapFeature = Feature<Geometry, { kind?: string }>;

function makeMarkerElement(label: string, color: string) {
  const el = document.createElement("div");
  el.textContent = label;
  el.style.width = "26px";
  el.style.height = "26px";
  el.style.borderRadius = "50%";
  el.style.background = "#fff";
  el.style.border = `2px solid ${color}`;
  el.style.color = color;
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.fontSize = "12px";
  el.style.fontWeight = "700";
  el.style.boxShadow = "0 2px 6px rgba(0,0,0,0.24)";
  return el;
}

export default function MapLibreMap({
  center,
  zoom,
  waypoints = [],
  droneCenter = null,
  userCenter = null,
  onPickLatLng,
  drawMode = "none",
  onDrawComplete,
  fieldBoundary = null,
  plannedRoute = null,
  exclusionZones = [],
  height = 400,
}: MapLibreMapProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMapInstance | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const drawingRef = useRef<LonLat[]>([]);
  const freehandDrawingRef = useRef(false);
  const drawModeRef = useRef(drawMode);
  const onDrawCompleteRef = useRef(onDrawComplete);
  const onPickRef = useRef(onPickLatLng);

  useEffect(() => {
    onPickRef.current = onPickLatLng;
  }, [onPickLatLng]);
  function updateDrawingPreview(
    map: MapLibreMapInstance | null,
    mode: FlatDrawMode,
    coords: LonLat[],
  ) {
    if (!map || !map.isStyleLoaded()) return;
    const previewCoords = shapePreview(mode, coords);
    const features: MapFeature[] = coords.map(([lng, lat]) => ({
      type: "Feature",
      properties: { kind: "point" },
      geometry: { type: "Point", coordinates: [lng, lat] },
    }));
    if (mode === "polyline" && previewCoords.length >= 2) {
      features.push({
        type: "Feature",
        properties: { kind: "line" },
        geometry: { type: "LineString", coordinates: previewCoords },
      });
    }
    if (["polygon", "rectangle", "circle", "triangle", "freehand"].includes(mode) && previewCoords.length >= 3) {
      features.push({
        type: "Feature",
        properties: { kind: "polygon" },
        geometry: { type: "Polygon", coordinates: [closeRing(previewCoords)] },
      });
    }

    const data = { type: "FeatureCollection" as const, features };
    const source = map.getSource(drawSourceId) as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(data);
      return;
    }

    map.addSource(drawSourceId, { type: "geojson", data });
    map.addLayer({
      id: drawFillLayerId,
      type: "fill",
      source: drawSourceId,
      filter: ["==", ["get", "kind"], "polygon"],
      paint: { "fill-color": "#1976d2", "fill-opacity": 0.16 },
    });
    map.addLayer({
      id: drawLineLayerId,
      type: "line",
      source: drawSourceId,
      filter: ["in", ["get", "kind"], ["literal", ["line", "polygon"]]],
      paint: { "line-color": "#1976d2", "line-width": 3, "line-dasharray": [2, 2] },
    });
    map.addLayer({
      id: drawPointLayerId,
      type: "circle",
      source: drawSourceId,
      filter: ["==", ["get", "kind"], "point"],
      paint: {
        "circle-radius": 5,
        "circle-color": "#1976d2",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
      },
    });
  }

  useEffect(() => {
    drawModeRef.current = drawMode;
    drawingRef.current = [];
    updateDrawingPreview(mapRef.current, drawMode, []);
    if (mapRef.current) {
      if (drawMode === "none") mapRef.current.doubleClickZoom.enable();
      else mapRef.current.doubleClickZoom.disable();
    }
  }, [drawMode]);

  useEffect(() => {
    onDrawCompleteRef.current = onDrawComplete;
  }, [onDrawComplete]);

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: hostRef.current,
      center: [center.lng, center.lat],
      zoom,
      style: "https://tiles.stadiamaps.com/styles/alidade_smooth.json",
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.once("load", () => {
      setTimeout(() => map.resize(), 0);
      updateDrawingPreview(map, drawModeRef.current, drawingRef.current);
    });
    map.on("click", (event: maplibregl.MapMouseEvent) => {
      const mode = drawModeRef.current;
      if (mode !== "none") {
        const coord: LonLat = [event.lngLat.lng, event.lngLat.lat];
        if (mode === "point") {
          onDrawCompleteRef.current?.({ type: "point", coordinates: coord });
          return;
        }
        if (mode === "rectangle" || mode === "circle" || mode === "triangle") {
          drawingRef.current =
            drawingRef.current.length === 0
              ? [coord]
              : [drawingRef.current[0], coord];
          updateDrawingPreview(map, mode, drawingRef.current);
          return;
        }
        if (mode === "freehand") return;
        drawingRef.current = [...drawingRef.current, coord];
        updateDrawingPreview(map, mode, drawingRef.current);
        return;
      }
      onPickRef.current?.({ lat: event.lngLat.lat, lng: event.lngLat.lng });
    });
    const finishDrawing = () => {
      const mode = drawModeRef.current;
      const coords = drawingRef.current;
      const result = completeShape(mode, coords);
      if (result) onDrawCompleteRef.current?.(result);
      drawingRef.current = [];
      freehandDrawingRef.current = false;
      updateDrawingPreview(map, mode, []);
    };
    map.on("mousedown", (event: maplibregl.MapMouseEvent) => {
      if (drawModeRef.current !== "freehand") return;
      freehandDrawingRef.current = true;
      map.dragPan.disable();
      drawingRef.current = [[event.lngLat.lng, event.lngLat.lat]];
      updateDrawingPreview(map, "freehand", drawingRef.current);
    });
    map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
      const mode = drawModeRef.current;
      const coord: LonLat = [event.lngLat.lng, event.lngLat.lat];
      if ((mode === "rectangle" || mode === "circle" || mode === "triangle") && drawingRef.current.length === 1) {
        drawingRef.current = [drawingRef.current[0], coord];
        updateDrawingPreview(map, mode, drawingRef.current);
        return;
      }
      if (mode !== "freehand" || !freehandDrawingRef.current) return;
      drawingRef.current = [...drawingRef.current, coord];
      updateDrawingPreview(map, mode, drawingRef.current);
    });
    map.on("mouseup", () => {
      if (drawModeRef.current !== "freehand" || !freehandDrawingRef.current) return;
      map.dragPan.enable();
      finishDrawing();
    });
    map.on("dblclick", finishDrawing);
    map.on("contextmenu", finishDrawing);
    mapRef.current = map;

    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    mapRef.current?.jumpTo({ center: [center.lng, center.lat], zoom });
  }, [center, zoom]);

  const routeCoordinates = useMemo(
    () => waypoints.map((point) => [point.lon, point.lat]),
    [waypoints],
  );

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    waypoints.forEach((point, index) => {
      markersRef.current.push(
        new maplibregl.Marker({ element: makeMarkerElement(String(index + 1), "#1976d2") })
          .setLngLat([point.lon, point.lat])
          .addTo(map),
      );
    });

    if (droneCenter) {
      markersRef.current.push(
        new maplibregl.Marker({ element: makeMarkerElement("D", "#1976d2") })
          .setLngLat([droneCenter.lng, droneCenter.lat])
          .addTo(map),
      );
    }

    if (userCenter) {
      markersRef.current.push(
        new maplibregl.Marker({ element: makeMarkerElement("U", "#2e7d32") })
          .setLngLat([userCenter.lng, userCenter.lat])
          .addTo(map),
      );
    }

    const updateRoute = () => {
      const data =
        routeCoordinates.length >= 2
          ? {
              type: "Feature" as const,
              properties: {},
              geometry: {
                type: "LineString" as const,
                coordinates: routeCoordinates,
              },
            }
          : {
              type: "FeatureCollection" as const,
              features: [],
            };

      const source = map.getSource(routeSourceId) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(data);
        return;
      }

      map.addSource(routeSourceId, { type: "geojson", data });
      map.addLayer({
        id: routeLayerId,
        type: "line",
        source: routeSourceId,
        paint: {
          "line-color": "#1976d2",
          "line-width": 3,
          "line-opacity": 0.85,
        },
      });
    };

    if (map.loaded()) {
      updateRoute();
    } else {
      map.once("load", updateRoute);
    }
  }, [droneCenter, routeCoordinates, userCenter, waypoints]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateOverlays = () => {
      const features: MapFeature[] = [];
      if (fieldBoundary && fieldBoundary.length >= 3) {
        features.push({
          type: "Feature",
          properties: { kind: "field" },
          geometry: { type: "Polygon", coordinates: [[...fieldBoundary, fieldBoundary[0]]] },
        });
      }
      exclusionZones.forEach((zone) => {
        if (zone.length < 3) return;
        features.push({
          type: "Feature",
          properties: { kind: "exclusion" },
          geometry: { type: "Polygon", coordinates: [[...zone, zone[0]]] },
        });
      });
      if (plannedRoute && plannedRoute.length >= 2) {
        features.push({
          type: "Feature",
          properties: { kind: "planned" },
          geometry: { type: "LineString", coordinates: plannedRoute },
        });
      }

      const data = { type: "FeatureCollection" as const, features };
      const source = map.getSource(overlaySourceId) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(data);
        return;
      }

      map.addSource(overlaySourceId, { type: "geojson", data });
      map.addLayer({
        id: overlayFillLayerId,
        type: "fill",
        source: overlaySourceId,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": ["case", ["==", ["get", "kind"], "exclusion"], "#d32f2f", "#1565c0"],
          "fill-opacity": ["case", ["==", ["get", "kind"], "exclusion"], 0.24, 0.12],
        },
      });
      map.addLayer({
        id: overlayLineLayerId,
        type: "line",
        source: overlaySourceId,
        paint: {
          "line-color": [
            "case",
            ["==", ["get", "kind"], "exclusion"],
            "#b71c1c",
            ["==", ["get", "kind"], "planned"],
            "#2e7d32",
            "#1565c0",
          ],
          "line-width": ["case", ["==", ["get", "kind"], "planned"], 4, 2],
        },
      });
    };

    if (map.loaded()) updateOverlays();
    else map.once("load", updateOverlays);
  }, [exclusionZones, fieldBoundary, plannedRoute]);

  if (!Number.isFinite(center.lat) || !Number.isFinite(center.lng)) {
    return (
      <Box
        sx={{
          width: "100%",
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "background.paper",
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Map center unavailable.
        </Typography>
      </Box>
    );
  }

  return <div ref={hostRef} style={{ width: "100%", height, minHeight: 320 }} />;
}
