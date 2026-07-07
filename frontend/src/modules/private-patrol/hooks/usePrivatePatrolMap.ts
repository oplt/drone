import { useCallback, useEffect, useMemo, useState } from "react";
import type { TerraDraw } from "terra-draw";
import { type LatLng } from "../../../shared/utils/extractLatLng";
import {
  terraDrawToolToShapeMode,
  type CesiumDrawResult,
  type DrawMode,
  type MissionMapEngine,
  type TerraDrawEditorMode,
  type TerraDrawToolMode,
} from "../../maps";
import { computeRingMapViewport, stripClosedRing, type LonLat } from "../../fields";
import { createFlatBoundaryDrawBridge } from "../../maps/utils/flatBoundaryDrawBridge";
import {
  useGooglePointMarkers,
  type GooglePointMarker,
} from "../../maps/hooks/useGooglePointMarkers";
import { useMissionMapRuntime } from "../../maps/hooks/useMissionMapRuntime";
import { useSyncTerraDrawMode } from "../../maps/hooks/useSyncTerraDrawMode";
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
  selectedField,
  mapEngine: controlledMapEngine,
  addError,
  onMapEngineChange,
  fieldPolygonRef,
  terraDrawRef,
  onBoundaryDrawStarted,
  resetBoundaryDrawSession,
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
  selectedField: { ring: LonLat[] } | null;
  mapEngine: MissionMapEngine;
  addError: (message: string) => void;
  onMapEngineChange: (engine: MissionMapEngine) => void;
  fieldPolygonRef: React.MutableRefObject<google.maps.Polygon | null>;
  terraDrawRef: React.MutableRefObject<TerraDraw | null>;
  onBoundaryDrawStarted?: () => void;
  resetBoundaryDrawSession?: () => void;
}) {
  const flatBoundaryDraw = useMemo(
    () =>
      createFlatBoundaryDrawBridge({
        setFieldBorder,
        setSelectedFieldId,
        onBoundaryDrawStarted,
      }),
    [onBoundaryDrawStarted, setFieldBorder, setSelectedFieldId],
  );

  const handleLocationError = useCallback((error: GeolocationPositionError) => {
    console.error("Error getting location:", error);
    const message = `Failed to get location: ${error.message}`;
    addError(message);
    return message;
  }, [addError]);

  const mapRuntime = useMissionMapRuntime({
    apiBase,
    wsConnected,
    droneConnected,
    telemetry,
    activeFlightId,
    fieldTilesetUrl,
    controlledMapEngine,
    onMapEngineChange,
    fieldPolygonRef,
    onAutoStartVideoError: addError,
    onLocationError: handleLocationError,
  });
  const {
    mapRef,
    lastSyncedCenterRef,
    center,
    setCenter,
    mapZoom,
    setMapZoom,
    mapReady,
    mapEngine,
  } = mapRuntime;

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
      resetBoundaryDrawSession?.();
      if (mapEngine !== "google") {
        setDrawMode(terraDrawToolToShapeMode(toolMode));
        return;
      }

      setTerraDrawMode(toolMode);
    },
    [mapEngine, resetBoundaryDrawSession, setDrawMode, setTerraDrawMode]
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
            })),
          );
        } else {
          const ring = stripClosedRing(
            result.coordinates.map(([lon, lat]) => [lon, lat] as LonLat),
          );
          if (ring.length >= 3) {
            setFieldBorder(ring);
            setSelectedFieldId(null);
          }
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
    [lastSyncedCenterRef, mapEngine, mapRef, setCenter, setMapZoom],
  );

  useSyncTerraDrawMode({ drawMode, mapEngine, setTerraDrawMode });

  const pointMarkers = useMemo<GooglePointMarker[]>(() => {
    if (gridParams.task_type === "waypoint_patrol" && waypoints.length > 0) {
      return waypoints.map((point) => ({
        point,
        title: "Waypoint",
        color: "#1976d2",
      }));
    }

    if (gridParams.event_triggered_enabled && eventLocation) {
      return [
        {
          point: eventLocation,
          title: "Event Location",
          color: "#d32f2f",
        },
      ];
    }

    return [];
  }, [eventLocation, gridParams.event_triggered_enabled, gridParams.task_type, waypoints]);

  useGooglePointMarkers({
    enabled: terraDrawMode === "static",
    isLoaded: mapRuntime.isLoaded,
    mapReady,
    mapRef,
    markersRef: mapRuntime.waypointMarkersRef,
    markers: pointMarkers,
  });

  useEffect(() => {
    if (!selectedField) return;
    if (mapEngine === "google" && mapReady) {
      loadRingIntoEditor(selectedField.ring);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    focusFieldRing(selectedField.ring);
  }, [focusFieldRing, loadRingIntoEditor, mapEngine, mapReady, selectedField]);

  const mapCenter = useMemo(
    () => fieldFocusViewport?.center ?? mapRuntime.droneCenter ?? mapRuntime.userCenter ?? center,
    [fieldFocusViewport, mapRuntime.droneCenter, mapRuntime.userCenter, center],
  );

  const effectiveMapZoom = fieldFocusViewport?.zoom ?? mapZoom;

  const cesiumFieldBoundary = useMemo(
    () => (fieldBorder && fieldBorder.length >= 3 ? fieldBorder : null),
    [fieldBorder]
  );

  return {
    containerStyle: mapRuntime.containerStyle,
    mapRef,
    terraDrawRef,
    terraDrawReady: mapRuntime.terraDrawReady,
    setTerraDrawReady: mapRuntime.setTerraDrawReady,
    mapReady,
    mapEngine,
    useCesium: mapEngine === "cesium",
    handleMapEngineChange: mapRuntime.handleMapEngineChange,
    cesiumViewMode: mapRuntime.cesiumViewMode,
    setCesiumViewMode: mapRuntime.setCesiumViewMode,
    mapZoom: effectiveMapZoom,
    mapCenter,
    fieldFocusRequest: fieldFocusViewport
      ? { ring: fieldFocusViewport.ring, token: fieldFocusViewport.token }
      : null,
    mapOptions: mapRuntime.mapOptions,
    loadingLocation: mapRuntime.loadingLocation,
    isLoaded: mapRuntime.isLoaded,
    loadError: mapRuntime.loadError,
    apiKey: mapRuntime.apiKey,
    mapId: mapRuntime.mapId,
    streamKey: mapRuntime.streamKey,
    setStreamKey: mapRuntime.setStreamKey,
    videoToken: mapRuntime.videoToken,
    startingVideo: mapRuntime.startingVideo,
    videoError: mapRuntime.videoError,
    videoRetryCount: mapRuntime.videoRetryCount,
    droneCenter: mapRuntime.droneCenter,
    heading: mapRuntime.heading,
    armed: mapRuntime.armed,
    onMapLoad: mapRuntime.onMapLoad,
    onMapUnmount: mapRuntime.onMapUnmount,
    onMapZoomChanged: mapRuntime.onMapZoomChanged,
    onMapCenterChanged: mapRuntime.onMapCenterChanged,
    onMapClick,
    handleDrawingToolSelection,
    handleCesiumDrawComplete,
    onBoundaryDrawStarted: flatBoundaryDraw.onBoundaryDrawStarted,
    onBoundaryDrawProgress: flatBoundaryDraw.onBoundaryDrawProgress,
    handleVideoError: mapRuntime.handleVideoError,
    handleVideoLoad: mapRuntime.handleVideoLoad,
    handleVideoRetry: mapRuntime.handleVideoRetry,
    focusFieldRing,
    cesiumFieldBoundary,
    userCenter: mapRuntime.userCenter,
    syncFieldBorderFromSnapshot,
    isRemovableUserDrawingFeature,
    terraDrawMode,
    setTerraDrawMode,
  };
}
