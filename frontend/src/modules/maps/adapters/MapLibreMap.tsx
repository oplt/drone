import { useCallback, useEffect, useMemo, useRef } from "react";
import { Box, Typography } from "@mui/material";
import type { Map as MapLibreMapInstance, Marker } from "maplibre-gl";
import type { Feature, Geometry } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import maplibregl from "maplibre-gl";
import {
  closeRing,
  shapePreview,
  type ShapeDrawMode,
  type ShapeDrawResult,
} from "../../../modules/maps/utils/drawingShapes";
import droneIconUrl from "../../../assets/Drone.svg?url";
import { useFlatMapDrawing } from "../hooks/useFlatMapDrawing";
import { ringLatLngBounds } from "../../fields";
import { isNearLonLat, isNearLonLatPixels } from "../utils/flatMapShapeGeometry";

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt?: number };
type LonLat = [number, number];
type SavedFieldBoundary = { id: number; name?: string | null; ring: LonLat[] };
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
  onBoundaryDrawStarted?: () => void;
  onBoundaryDrawProgress?: (coords: LonLat[]) => void;
  fieldBoundary?: LonLat[] | null;
  savedFields?: SavedFieldBoundary[];
  selectedFieldId?: number | null;
  onSavedFieldClick?: (fieldId: number) => void;
  onFieldBoundaryClick?: () => void;
  drawnBoundarySelected?: boolean;
  plannedRoute?: LonLat[] | null;
  exclusionZones?: LonLat[][];
  height?: number | string;
  focusRing?: LonLat[] | null;
  focusRequestToken?: number;
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
type MapFeature = Feature<
  Geometry,
  { kind?: string; fieldId?: number; selected?: boolean }
>;

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

function makeDroneMarkerElement() {
  const el = document.createElement("div");
  el.style.width = "40px";
  el.style.height = "40px";
  el.style.filter = "drop-shadow(0 2px 4px rgba(0,0,0,0.35))";

  const img = document.createElement("img");
  img.src = droneIconUrl;
  img.alt = "Drone";
  img.style.width = "40px";
  img.style.height = "40px";
  img.style.display = "block";
  el.appendChild(img);

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
  onBoundaryDrawStarted,
  onBoundaryDrawProgress,
  fieldBoundary = null,
  savedFields = [],
  selectedFieldId = null,
  onSavedFieldClick,
  onFieldBoundaryClick,
  drawnBoundarySelected = false,
  plannedRoute = null,
  exclusionZones = [],
  height = 400,
  focusRing = null,
  focusRequestToken,
}: MapLibreMapProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMapInstance | null>(null);
  const waypointMarkersRef = useRef<Marker[]>([]);
  const droneMarkerRef = useRef<Marker | null>(null);
  const userMarkerRef = useRef<Marker | null>(null);
  const drawingRef = useRef<ReturnType<typeof useFlatMapDrawing> | null>(null);
  const onSavedFieldClickRef = useRef<MapLibreMapProps["onSavedFieldClick"]>(
    onSavedFieldClick,
  );
  const onFieldBoundaryClickRef = useRef<MapLibreMapProps["onFieldBoundaryClick"]>(
    onFieldBoundaryClick,
  );
  const drawModeRef = useRef(drawMode);
  const setDrawingModeState = useCallback((mode: FlatDrawMode) => {
    if (!mapRef.current) return;
    if (mode === "none") mapRef.current.doubleClickZoom.enable();
    else mapRef.current.doubleClickZoom.disable();
  }, []);
  const isNearCoord = useCallback((a: LonLat, b: LonLat) => {
    const map = mapRef.current;
    if (map) {
      return isNearLonLatPixels(map, a, b) || isNearLonLat(a, b);
    }
    return isNearLonLat(a, b);
  }, []);
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
  drawingRef.current = drawing;
  onSavedFieldClickRef.current = onSavedFieldClick;
  onFieldBoundaryClickRef.current = onFieldBoundaryClick;

  drawModeRef.current = drawMode;

  function updateDrawingPreview(mode: FlatDrawMode, coords: LonLat[]) {
    const map = mapRef.current;
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
    if (
      ["polygon", "rectangle", "circle", "triangle", "freehand"].includes(
        mode,
      ) &&
      previewCoords.length >= 3
    ) {
      features.push({
        type: "Feature",
        properties: { kind: "polygon" },
        geometry: { type: "Polygon", coordinates: [closeRing(previewCoords)] },
      });
    }

    const data = { type: "FeatureCollection" as const, features };
    const source = map.getSource(drawSourceId) as
      | maplibregl.GeoJSONSource
      | undefined;
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
      paint: {
        "line-color": "#1976d2",
        "line-width": 3,
        "line-dasharray": [2, 2],
      },
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
    if (!hostRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: hostRef.current,
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
      updateDrawingPreview("none", []);
    });
    map.on("click", (event: maplibregl.MapMouseEvent) => {
      if (drawModeRef.current !== "none") {
        drawingRef.current?.handleClick([event.lngLat.lng, event.lngLat.lat]);
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
            onSavedFieldClickRef.current?.(fieldId);
            return;
          }
          if (typeof fieldId === "string") {
            onSavedFieldClickRef.current?.(Number(fieldId));
            return;
          }
        }
        const drawnBoundary = overlayFeatures.find(
          (item) => item.properties?.kind === "field",
        );
        if (drawnBoundary) {
          onFieldBoundaryClickRef.current?.();
          return;
        }
      }
      drawingRef.current?.handleClick([event.lngLat.lng, event.lngLat.lat]);
    });
    map.on("mousedown", (event: maplibregl.MapMouseEvent) => {
      if (drawingRef.current?.startFreehand([event.lngLat.lng, event.lngLat.lat]))
        map.dragPan.disable();
    });
    map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
      drawingRef.current?.movePointer([event.lngLat.lng, event.lngLat.lat]);
    });
    map.on("mouseup", () => {
      if (drawingRef.current?.endFreehand()) map.dragPan.enable();
    });
    map.on("dblclick", (event) => {
      event.preventDefault();
      if (drawModeRef.current !== "none") {
        drawingRef.current?.finishDrawing();
      }
    });
    map.on("contextmenu", (event) => {
      event.preventDefault();
      if (drawModeRef.current !== "none") {
        drawingRef.current?.finishDrawing();
      }
    });
    map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
      if (!map.getLayer(overlayFillLayerId)) return;
      const hasSavedField = map
        .queryRenderedFeatures(event.point, { layers: [overlayFillLayerId] })
        .some((item) => item.properties?.kind === "saved-field");
      map.getCanvas().style.cursor = hasSavedField ? "pointer" : "";
    });
    mapRef.current = map;

    return () => {
      waypointMarkersRef.current.forEach((marker) => marker.remove());
      waypointMarkersRef.current = [];
      droneMarkerRef.current?.remove();
      droneMarkerRef.current = null;
      userMarkerRef.current?.remove();
      userMarkerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    mapRef.current?.jumpTo({ center: [center.lng, center.lat], zoom });
  }, [center, zoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || focusRequestToken == null) return;
    const bounds = focusRing ? ringLatLngBounds(focusRing) : null;
    if (!bounds) return;
    const fit = new maplibregl.LngLatBounds(
      [bounds.west, bounds.south],
      [bounds.east, bounds.north],
    );
    map.fitBounds(fit, { padding: 40, duration: 500 });
  }, [focusRing, focusRequestToken]);

  const routeCoordinates = useMemo(
    () => waypoints.map((point) => [point.lon, point.lat]),
    [waypoints],
  );

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    waypointMarkersRef.current.forEach((marker) => marker.remove());
    waypointMarkersRef.current = [];

    waypoints.forEach((point, index) => {
      waypointMarkersRef.current.push(
        new maplibregl.Marker({
          element: makeMarkerElement(String(index + 1), "#1976d2"),
        })
          .setLngLat([point.lon, point.lat])
          .addTo(map),
      );
    });

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

      const source = map.getSource(routeSourceId) as
        | maplibregl.GeoJSONSource
        | undefined;
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
  }, [routeCoordinates, waypoints]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (droneCenter) {
      if (!droneMarkerRef.current) {
        droneMarkerRef.current = new maplibregl.Marker({
          element: makeDroneMarkerElement(),
        })
          .setLngLat([droneCenter.lng, droneCenter.lat])
          .addTo(map);
      } else {
        droneMarkerRef.current.setLngLat([droneCenter.lng, droneCenter.lat]);
      }
    } else if (droneMarkerRef.current) {
      droneMarkerRef.current.remove();
      droneMarkerRef.current = null;
    }
  }, [droneCenter]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (userCenter) {
      if (!userMarkerRef.current) {
        userMarkerRef.current = new maplibregl.Marker({
          element: makeMarkerElement("U", "#2e7d32"),
        })
          .setLngLat([userCenter.lng, userCenter.lat])
          .addTo(map);
      } else {
        userMarkerRef.current.setLngLat([userCenter.lng, userCenter.lat]);
      }
    } else if (userMarkerRef.current) {
      userMarkerRef.current.remove();
      userMarkerRef.current = null;
    }
  }, [userCenter]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateOverlays = () => {
      const features: MapFeature[] = [];
      savedFields.forEach((field) => {
        if (field.ring.length < 3) return;
        features.push({
          type: "Feature",
          properties: {
            kind: "saved-field",
            fieldId: field.id,
            selected: field.id === selectedFieldId,
          },
          geometry: {
            type: "Polygon",
            coordinates: [[...field.ring, field.ring[0]]],
          },
        });
      });
      if (drawMode === "none" && fieldBoundary && fieldBoundary.length >= 3) {
        features.push({
          type: "Feature",
          properties: { kind: "field", selected: drawnBoundarySelected },
          geometry: {
            type: "Polygon",
            coordinates: [[...fieldBoundary, fieldBoundary[0]]],
          },
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
      const source = map.getSource(overlaySourceId) as
        | maplibregl.GeoJSONSource
        | undefined;
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
          "fill-color": [
            "case",
            ["==", ["get", "kind"], "exclusion"],
            "#d32f2f",
            ["==", ["get", "selected"], true],
            "#1976d2",
            "#1565c0",
          ],
          "fill-opacity": [
            "case",
            ["==", ["get", "kind"], "exclusion"],
            0.24,
            ["==", ["get", "kind"], "saved-field"],
            0.08,
            0.12,
          ],
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
            ["==", ["get", "selected"], true],
            "#1976d2",
            "#1565c0",
          ],
          "line-width": [
            "case",
            ["==", ["get", "kind"], "planned"],
            4,
            ["all", ["==", ["get", "kind"], "field"], ["==", ["get", "selected"], true]],
            4,
            ["==", ["get", "selected"], true],
            4,
            2,
          ],
        },
      });
    };

    if (map.loaded()) updateOverlays();
    else map.once("load", updateOverlays);
  }, [drawMode, exclusionZones, fieldBoundary, plannedRoute, savedFields, selectedFieldId, drawnBoundarySelected]);

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

  return (
    <div ref={hostRef} style={{ width: "100%", height, minHeight: 320 }} />
  );
}
