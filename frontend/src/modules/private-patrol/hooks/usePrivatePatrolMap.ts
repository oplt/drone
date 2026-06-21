import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { TerraDraw } from "terra-draw";
import { getToken } from "../../../modules/session";
import { useAutoStartVideo } from "../../../modules/mission-runtime";
import { type LatLng } from "../../../shared/utils/extractLatLng";
import {
  GoogleMapsContext,
  useDroneCenter,
  useDroneMapFollow,
  terraDrawToolToShapeMode,
  type CesiumDrawResult,
  type CesiumViewMode,
  type DrawMode,
  type MissionMapEngine,
  type TerraDrawEditorMode,
  type TerraDrawToolMode,
} from "../../maps";
import { useMissionCommandMetrics } from "../../mission-runtime";
import { computeRingMapViewport, stripClosedRing, type LonLat } from "../../fields";
import type { PatrolGridParams, Waypoint } from "../types";

export function usePrivatePatrolMap({
  apiBase,
  wsConnected,
  droneConnected,
  telemetry,
  activeFlightId,
  fieldBorder,
  setFieldBorder,
  setSelectedFieldId,
  fieldTilesetUrl,
  waypoints,
  setWaypoints,
  eventLocation,
  setEventLocation,
  alt,
  gridParams,
  drawMode,
  setDrawMode,
  terraDrawMode,
  setTerraDrawMode,
  syncFieldBorderFromSnapshot,
  isRemovableUserDrawingFeature,
  loadRingIntoEditor,
  focusRingOnMap,
  selectedField,
  mapEngine: controlledMapEngine,
  addError,
  onMapEngineChange,
  fieldPolygonRef,
  terraDrawRef,
}: {
  apiBase: string;
  wsConnected: boolean;
  droneConnected: boolean;
  telemetry: unknown;
  activeFlightId: string | null;
  fieldBorder: LonLat[] | null;
  setFieldBorder: (border: LonLat[] | null) => void;
  setSelectedFieldId: (id: number | null) => void;
  fieldTilesetUrl: string | null | undefined;
  waypoints: Waypoint[];
  setWaypoints: React.Dispatch<React.SetStateAction<Waypoint[]>>;
  eventLocation: Waypoint | null;
  setEventLocation: React.Dispatch<React.SetStateAction<Waypoint | null>>;
  alt: number;
  gridParams: PatrolGridParams;
  drawMode: DrawMode;
  setDrawMode: (mode: DrawMode) => void;
  terraDrawMode: TerraDrawEditorMode;
  setTerraDrawMode: (mode: TerraDrawEditorMode) => void;
  syncFieldBorderFromSnapshot: (
    snapshot: import("../../mission-workflow").TerraFeature[]
  ) => void;
  isRemovableUserDrawingFeature: (
    feature: import("../../mission-workflow").TerraFeature
  ) => boolean;
  loadRingIntoEditor: (ring: LonLat[]) => void;
  focusRingOnMap: (ring: LonLat[]) => void;
  selectedField: { ring: LonLat[] } | null;
  mapEngine: MissionMapEngine;
  addError: (message: string) => void;
  onMapEngineChange: (engine: MissionMapEngine) => void;
  fieldPolygonRef: React.MutableRefObject<google.maps.Polygon | null>;
  terraDrawRef: React.MutableRefObject<TerraDraw | null>;
}) {
  const containerStyle = { width: "100%", height: "400px" };
  const defaultCenter = { lat: 50.8503, lng: 4.3517 };
  const mapRef = useRef<google.maps.Map | null>(null);
  const [terraDrawReady, setTerraDrawReady] = useState(false);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [center, setCenter] = useState(defaultCenter);
  const [loadingLocation, setLoadingLocation] = useState(true);
  const [mapZoom, setMapZoom] = useState(12);
  const [manualStreamKey, setManualStreamKey] = useState(0);
  const [mapReady, setMapReady] = useState(false);
  const mapEngine = controlledMapEngine;
  const [cesiumViewMode, setCesiumViewMode] = useState<CesiumViewMode>("tilted");
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoRetryCount, setVideoRetryCount] = useState(0);
  const waypointMarkersRef = useRef<unknown[]>([]);
  const lastSyncedCenterRef = useRef<LatLng | null>(null);
  const videoToken = getToken();

  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";

  const { isLoaded, loadError } = useContext(GoogleMapsContext);
  const droneCenter = useDroneCenter(telemetry);
  const { heading, armed } = useMissionCommandMetrics(telemetry);
  const droneReady = Boolean(droneConnected);

  const { startingVideo, streamKey: autoStreamKey } = useAutoStartVideo({
    apiBase,
    getToken,
    enabled: droneReady,
    onError: addError,
    resetKey: activeFlightId ?? "none",
  });

  useEffect(() => {
    if (!droneConnected) {
      setManualStreamKey(0);
    }
  }, [droneConnected]);

  const streamKey = manualStreamKey || autoStreamKey;

  const handleMapEngineChange = useCallback(
    (next: MissionMapEngine) => {
      onMapEngineChange(next);
    },
    [onMapEngineChange]
  );

  useEffect(() => {
    if (!fieldTilesetUrl) return;
    handleMapEngineChange("cesium");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCesiumViewMode("top");
  }, [fieldTilesetUrl, handleMapEngineChange]);

  useEffect(() => {
    if (!navigator.geolocation) {
      console.warn("Geolocation is not supported by this browser.");
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoadingLocation(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const userLocation = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        setUserCenter(userLocation);
        setCenter(userLocation);
        setLoadingLocation(false);
      },
      (error) => {
        console.error("Error getting location:", error);
        addError(`Failed to get location: ${error.message}`);
        setLoadingLocation(false);
      },
      {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 0,
      }
    );
  }, [addError]);

  const onMapLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setMapReady(true);
  }, []);

  const onMapUnmount = useCallback(() => {
    if (fieldPolygonRef.current) {
      fieldPolygonRef.current.setMap(null);
      fieldPolygonRef.current = null;
    }
    mapRef.current = null;
    setMapReady(false);
  }, [fieldPolygonRef]);

  const onMapZoomChanged = useCallback(() => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (typeof zoom === "number" && Number.isFinite(zoom)) {
      setMapZoom(zoom);
    }
  }, []);

  const onMapCenterChanged = useCallback(() => {
    if (!mapRef.current) return;

    const mapCenter = mapRef.current.getCenter();
    if (!mapCenter) return;

    const newCenter = { lat: mapCenter.lat(), lng: mapCenter.lng() };
    const last = lastSyncedCenterRef.current;

    const hasChanged =
      !last ||
      Math.abs(last.lat - newCenter.lat) > 0.00001 ||
      Math.abs(last.lng - newCenter.lng) > 0.00001;

    if (hasChanged) {
      lastSyncedCenterRef.current = newCenter;
      setCenter(newCenter);
    }
  }, []);

  useDroneMapFollow({
    mapRef,
    droneCenter,
    wsConnected,
    onInitialSnap: () => setMapZoom(18),
  });

  const onMapClick = useCallback(
    (e: google.maps.MapMouseEvent) => {
      if (terraDrawMode !== "static") return;
      if (!e.latLng) return;
      const lat = e.latLng.lat();
      const lng = e.latLng.lng();
      if (gridParams.task_type === "waypoint_patrol") {
        setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
        return;
      }
      if (gridParams.event_triggered_enabled) {
        setEventLocation({ lat, lon: lng, alt });
      }
    },
    [alt, gridParams.event_triggered_enabled, gridParams.task_type, setEventLocation, setWaypoints, terraDrawMode]
  );

  const handleDrawingToolSelection = useCallback(
    (toolMode: TerraDrawToolMode) => {
      if (mapEngine !== "google") {
        setDrawMode(terraDrawToolToShapeMode(toolMode));
        return;
      }

      setTerraDrawMode(toolMode);
    },
    [mapEngine, setDrawMode, setTerraDrawMode]
  );

  const handleCesiumDrawComplete = useCallback(
    (result: CesiumDrawResult) => {
      if (result.type === "polygon") {
        const ring = stripClosedRing(
          result.coordinates.map(([lon, lat]) => [lon, lat] as LonLat)
        );
        if (ring.length >= 3) {
          setFieldBorder(ring);
          setSelectedFieldId(null);
        }
      } else if (result.type === "polyline") {
        if (gridParams.task_type === "waypoint_patrol") {
          setWaypoints(
            result.coordinates.map(([lon, lat]) => ({
              lat,
              lon,
              alt,
            }))
          );
        }
      } else if (result.type === "point") {
        if (gridParams.task_type === "waypoint_patrol") {
          const [lon, lat] = result.coordinates;
          setWaypoints((prev) => [...prev, { lat, lon, alt }]);
        } else if (gridParams.event_triggered_enabled) {
          const [lon, lat] = result.coordinates;
          setEventLocation({ lat, lon, alt });
        }
      }

      setDrawMode("none");
    },
    [alt, gridParams.event_triggered_enabled, gridParams.task_type, setDrawMode, setEventLocation, setFieldBorder, setSelectedFieldId, setWaypoints]
  );

  const handleVideoError = useCallback(() => {
    setVideoError("Failed to load video stream");
    setVideoRetryCount((prev) => prev + 1);
  }, []);

  const handleVideoLoad = useCallback(() => {
    setVideoError(null);
    setVideoRetryCount(0);
  }, []);

  const handleVideoRetry = useCallback(() => {
    setManualStreamKey(Date.now());
    setVideoError(null);
  }, []);

  const [fieldFocusViewport, setFieldFocusViewport] = useState<{
    center: LatLng;
    zoom: number;
    ring: LonLat[];
    token: number;
  } | null>(null);

  const focusFieldRing = useCallback(
    (ring: LonLat[]) => {
      if (mapEngine === "google" && mapRef.current && window.google?.maps) {
        const pts = stripClosedRing(ring);
        if (pts.length >= 3) {
          const bounds = new google.maps.LatLngBounds();
          pts.forEach(([lon, lat]) => bounds.extend({ lat, lng: lon }));
          if (!bounds.isEmpty()) {
            mapRef.current.fitBounds(bounds);
          }
        }
      }

      const viewport = computeRingMapViewport(ring);
      if (!viewport) return;

      const token = Date.now();
      lastSyncedCenterRef.current = viewport.center;
      setCenter(viewport.center);
      setMapZoom(viewport.zoom);
      setFieldFocusViewport({
        center: viewport.center,
        zoom: viewport.zoom,
        ring,
        token,
      });
    },
    [mapEngine],
  );

  useEffect(() => {
    if (mapEngine !== "google") return;

    const modeMap: Partial<Record<DrawMode, TerraDrawEditorMode>> = {
      polygon: "polygon",
      polyline: "linestring",
      point: "point",
      rectangle: "rectangle",
      circle: "circle",
      freehand: "freehand",
      triangle: "polygon",
      none: "static",
    };

    const tdMode = modeMap[drawMode];
    if (tdMode) setTerraDrawMode(tdMode);
  }, [drawMode, mapEngine, setTerraDrawMode]);

  useEffect(() => {
    if (!isLoaded || !mapReady) return;
    if (!mapRef.current) return;
    const markerLib = (
      google.maps as unknown as {
        marker?: { AdvancedMarkerElement?: new (opts: unknown) => unknown };
      }
    )?.marker;
    const AdvancedMarkerElement = markerLib?.AdvancedMarkerElement;
    if (!AdvancedMarkerElement) {
      return;
    }

    waypointMarkersRef.current.forEach((marker) => {
      try {
        if (marker && typeof marker === "object") {
          if ("map" in marker) (marker as { map: null }).map = null;
          else if (
            "setMap" in marker &&
            typeof (marker as { setMap: (v: null) => void }).setMap === "function"
          ) {
            (marker as { setMap: (v: null) => void }).setMap(null);
          }
        }
      } catch {
        // ignore cleanup errors
      }
    });
    waypointMarkersRef.current = [];

    if (terraDrawMode !== "static") return;

    const markersToRender: Array<{ point: Waypoint; title: string; color: string }> = [];
    if (gridParams.task_type === "waypoint_patrol" && waypoints.length > 0) {
      waypoints.forEach((p) =>
        markersToRender.push({ point: p, title: "Waypoint", color: "#1976d2" })
      );
    } else if (gridParams.event_triggered_enabled && eventLocation) {
      markersToRender.push({
        point: eventLocation,
        title: "Event Location",
        color: "#d32f2f",
      });
    }
    if (markersToRender.length === 0) return;

    markersToRender.forEach(({ point, title, color }) => {
      const content = document.createElement("div");
      content.style.width = "12px";
      content.style.height = "12px";
      content.style.borderRadius = "50%";
      content.style.background = color;
      content.style.border = "2px solid #ffffff";
      content.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";

      const marker = new AdvancedMarkerElement({
        map: mapRef.current,
        position: { lat: point.lat, lng: point.lon },
        content,
        title,
      });

      waypointMarkersRef.current.push(marker);
    });

    return () => {
      waypointMarkersRef.current.forEach((marker) => {
        try {
          if (marker && typeof marker === "object") {
            if ("map" in marker) (marker as { map: null }).map = null;
            else if (
              "setMap" in marker &&
              typeof (marker as { setMap: (v: null) => void }).setMap === "function"
            ) {
              (marker as { setMap: (v: null) => void }).setMap(null);
            }
          }
        } catch {
          // ignore cleanup errors
        }
      });
      waypointMarkersRef.current = [];
    };
  }, [
    eventLocation,
    gridParams.event_triggered_enabled,
    gridParams.task_type,
    isLoaded,
    mapReady,
    terraDrawMode,
    waypoints,
  ]);

  useEffect(() => {
    if (!selectedField) return;
    if (mapEngine === "google" && mapReady) {
      loadRingIntoEditor(selectedField.ring);
    }
    focusFieldRing(selectedField.ring);
  }, [focusFieldRing, loadRingIntoEditor, mapEngine, mapReady, selectedField]);

  const mapCenter = useMemo(
    () => fieldFocusViewport?.center ?? droneCenter ?? userCenter ?? center,
    [fieldFocusViewport, droneCenter, userCenter, center],
  );

  const effectiveMapZoom = fieldFocusViewport?.zoom ?? mapZoom;

  const mapOptions = useMemo(
    () => ({
      streetViewControl: false,
      mapTypeControl: false,
      fullscreenControl: true,
      clickableIcons: false,
      keyboardShortcuts: false,
      gestureHandling: "greedy" as const,
      maxZoom: 20,
      minZoom: 3,
      ...(mapId ? { mapId } : {}),
    }),
    [mapId]
  );

  const cesiumFieldBoundary = useMemo(
    () => (fieldBorder && fieldBorder.length >= 3 ? fieldBorder : null),
    [fieldBorder]
  );

  return {
    containerStyle,
    mapRef,
    terraDrawRef,
    terraDrawReady,
    setTerraDrawReady,
    mapReady,
    mapEngine,
    useCesium: mapEngine === "cesium",
    handleMapEngineChange,
    cesiumViewMode,
    setCesiumViewMode,
    mapZoom: effectiveMapZoom,
    mapCenter,
    fieldFocusRequest: fieldFocusViewport
      ? { ring: fieldFocusViewport.ring, token: fieldFocusViewport.token }
      : null,
    mapOptions,
    loadingLocation,
    isLoaded,
    loadError,
    apiKey,
    mapId,
    streamKey,
    setStreamKey: setManualStreamKey,
    videoToken,
    startingVideo,
    videoError,
    videoRetryCount,
    droneCenter,
    heading,
    armed,
    onMapLoad,
    onMapUnmount,
    onMapZoomChanged,
    onMapCenterChanged,
    onMapClick,
    handleDrawingToolSelection,
    handleCesiumDrawComplete,
    handleVideoError,
    handleVideoLoad,
    handleVideoRetry,
    focusFieldRing,
    cesiumFieldBoundary,
    userCenter,
    syncFieldBorderFromSnapshot,
    isRemovableUserDrawingFeature,
    terraDrawMode,
    setTerraDrawMode,
  };
}
