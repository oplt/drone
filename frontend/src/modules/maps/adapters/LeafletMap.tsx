import { useCallback, useEffect, useMemo, useRef } from "react";
import { Box, Typography } from "@mui/material";
import type { LatLngExpression, Map as LeafletMapInstance } from "leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import {
  closeRing,
  shapePreview,
  type ShapeDrawMode,
  type ShapeDrawResult,
} from "./../utils/drawingShapes";
import droneIconUrl from "../../../assets/Drone.svg?url";
import { useFlatMapDrawing } from "../hooks/useFlatMapDrawing";

type LatLng = { lat: number; lng: number };
type Waypoint = { lat: number; lon: number; alt?: number };
type LonLat = [number, number];
export type FlatDrawMode = ShapeDrawMode;
export type FlatDrawResult = ShapeDrawResult;

export type LeafletMapProps = {
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

function toLatLng(p: LatLng): LatLngExpression {
  return [p.lat, p.lng];
}

function makeWaypointIcon(label: string) {
  return L.divIcon({
    className: "",
    html: `<div style="width:26px;height:26px;border-radius:50%;background:#fff;border:2px solid #1976d2;color:#1976d2;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,0.24)">${label}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

function makeDroneIcon() {
  return L.divIcon({
    className: "",
    html: `<img src="${droneIconUrl}" alt="Drone" style="width:40px;height:40px;display:block;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35))" />`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

export default function LeafletMap({
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
}: LeafletMapProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMapInstance | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const drawLayerRef = useRef<L.LayerGroup | null>(null);
  const setDrawingModeState = useCallback((mode: FlatDrawMode) => {
    if (!mapRef.current) return;
    if (mode === "none") mapRef.current.doubleClickZoom.enable();
    else mapRef.current.doubleClickZoom.disable();
  }, []);

  const updateDrawingPreview = useMemo(
    () => (mode: FlatDrawMode, coords: LonLat[]) => {
      const drawLayers = drawLayerRef.current;
      if (!drawLayers) return;

      drawLayers.clearLayers();
      const previewCoords = shapePreview(mode, coords);
      coords.forEach(([lng, lat]) => {
        L.circleMarker([lat, lng], {
          radius: 5,
          color: "#1976d2",
          fillColor: "#1976d2",
          fillOpacity: 0.9,
          weight: 2,
        }).addTo(drawLayers);
      });
      if (mode === "polyline" && previewCoords.length >= 2) {
        L.polyline(
          previewCoords.map(([lng, lat]) => [lat, lng] as LatLngExpression),
          { color: "#1976d2", weight: 3, opacity: 0.9, dashArray: "6 6" },
        ).addTo(drawLayers);
      }
      if (
        ["polygon", "rectangle", "circle", "triangle", "freehand"].includes(
          mode,
        ) &&
        previewCoords.length >= 3
      ) {
        L.polygon(
          closeRing(previewCoords).map(
            ([lng, lat]) => [lat, lng] as LatLngExpression,
          ),
          {
            color: "#1976d2",
            weight: 2,
            fillColor: "#1976d2",
            fillOpacity: 0.16,
          },
        ).addTo(drawLayers);
      }
    },
    [],
  );

  const drawing = useFlatMapDrawing({
    drawMode,
    onDrawComplete,
    onPickLatLng,
    onPreview: updateDrawingPreview,
    onModeStateChange: setDrawingModeState,
  });

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;

    const map = L.map(hostRef.current, {
      center: toLatLng(center),
      zoom,
      zoomControl: true,
      preferCanvas: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 20,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map);

    const layers = L.layerGroup().addTo(map);
    const drawLayers = L.layerGroup().addTo(map);
    layerRef.current = layers;
    drawLayerRef.current = drawLayers;
    mapRef.current = map;

    map.whenReady(() => {
      setTimeout(() => map.invalidateSize(), 0);
    });

    map.on("click", (event: L.LeafletMouseEvent) => {
      drawing.handleClick([event.latlng.lng, event.latlng.lat]);
    });
    map.on("mousedown", (event: L.LeafletMouseEvent) => {
      if (drawing.startFreehand([event.latlng.lng, event.latlng.lat]))
        map.dragging.disable();
    });
    map.on("mousemove", (event: L.LeafletMouseEvent) => {
      drawing.movePointer([event.latlng.lng, event.latlng.lat]);
    });
    map.on("mouseup", () => {
      if (drawing.endFreehand()) map.dragging.enable();
    });
    map.on("dblclick", drawing.finishDrawing);
    map.on("contextmenu", drawing.finishDrawing);

    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
      drawLayerRef.current = null;
    };
  }, [drawing]);

  useEffect(() => {
    mapRef.current?.setView(toLatLng(center), zoom);
  }, [center, zoom]);

  const route = useMemo(
    () => waypoints.map((p) => [p.lat, p.lon] as LatLngExpression),
    [waypoints],
  );

  useEffect(() => {
    const layers = layerRef.current;
    if (!layers) return;

    layers.clearLayers();

    const boundary = fieldBoundary ?? [];
    if (boundary.length >= 3) {
      L.polygon(
        boundary.map(([lng, lat]) => [lat, lng] as LatLngExpression),
        {
          color: "#1565c0",
          weight: 2,
          fillColor: "#1565c0",
          fillOpacity: 0.12,
        },
      ).addTo(layers);
    }

    exclusionZones.forEach((zone) => {
      if (zone.length < 3) return;
      L.polygon(
        zone.map(([lng, lat]) => [lat, lng] as LatLngExpression),
        {
          color: "#b71c1c",
          weight: 2,
          fillColor: "#d32f2f",
          fillOpacity: 0.24,
        },
      ).addTo(layers);
    });

    const planned = plannedRoute ?? [];
    if (planned.length >= 2) {
      L.polyline(
        planned.map(([lng, lat]) => [lat, lng] as LatLngExpression),
        { color: "#2e7d32", weight: 4, opacity: 0.85 },
      ).addTo(layers);
    }

    waypoints.forEach((point, index) => {
      L.marker([point.lat, point.lon], {
        icon: makeWaypointIcon(String(index + 1)),
      }).addTo(layers);
    });

    if (route.length >= 2) {
      L.polyline(route, { color: "#1976d2", weight: 3, opacity: 0.85 }).addTo(
        layers,
      );
    }

    if (droneCenter) {
      L.marker(toLatLng(droneCenter), {
        icon: makeDroneIcon(),
        zIndexOffset: 1000,
      })
        .bindTooltip("DRONE", { permanent: false })
        .addTo(layers);
    }

    if (userCenter) {
      L.circleMarker(toLatLng(userCenter), {
        radius: 7,
        color: "#2e7d32",
        fillColor: "#2e7d32",
        fillOpacity: 0.9,
      })
        .bindTooltip("You", { permanent: false })
        .addTo(layers);
    }
  }, [
    droneCenter,
    exclusionZones,
    fieldBoundary,
    plannedRoute,
    route,
    userCenter,
    waypoints,
  ]);

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
