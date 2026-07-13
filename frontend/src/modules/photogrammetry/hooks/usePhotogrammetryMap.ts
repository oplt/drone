import { useCallback, useEffect, useMemo } from "react";
import type { TerraDraw } from "terra-draw";
import {
  terraDrawToolToShapeMode,
  type CesiumDrawResult,
  type DrawMode,
  type MissionMapEngine,
  type TerraDrawEditorMode,
  type TerraDrawToolMode,
} from "../../maps";
import { stripClosedRing, type LonLat } from "../../fields";
import { createFlatBoundaryDrawBridge } from "../../maps/utils/flatBoundaryDrawBridge";
import {
  useGooglePointMarkers,
  type GooglePointMarker,
} from "../../maps/hooks/useGooglePointMarkers";
import { useMissionMapRuntime } from "../../maps/hooks/useMissionMapRuntime";
import { useSyncTerraDrawMode } from "../../maps/hooks/useSyncTerraDrawMode";
import type { Waypoint } from "../../mission-workflow"; import { frontendLogger } from "../../../shared/logging";

export function usePhotogrammetryMap({
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
  alt,
  drawMode,
  setDrawMode,
  terraDrawMode,
  setTerraDrawMode,
  loadRingIntoEditor,
  focusRingOnMap,
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
  alt: number;
  drawMode: DrawMode;
  setDrawMode: (mode: DrawMode) => void;
  terraDrawMode: TerraDrawEditorMode;
  setTerraDrawMode: (mode: TerraDrawEditorMode) => void;
  loadRingIntoEditor: (ring: LonLat[]) => void;
  focusRingOnMap: (ring: LonLat[]) => void;
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
    frontendLogger.error("frontend", "Error getting location", { message: error.message, code: error.code });
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
  const { mapRef, mapZoom, mapReady, mapEngine } = mapRuntime;

  const onMapClick = useCallback(
    (e: google.maps.MapMouseEvent) => {
      if (terraDrawMode !== "static") return;
      if (!e.latLng) return;
      const lat = e.latLng.lat();
      const lng = e.latLng.lng();
      setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
    },
    [alt, setWaypoints, terraDrawMode]
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
        const ring = stripClosedRing(
          result.coordinates.map(([lon, lat]) => [lon, lat] as LonLat),
        );
        if (ring.length >= 3) {
          setFieldBorder(ring);
          setSelectedFieldId(null);
        }
      } else if (result.type === "point") {
        const [lon, lat] = result.coordinates;
        setWaypoints((prev) => [...prev, { lat, lon, alt }]);
      }

      setDrawMode("none");
    },
    [alt, setDrawMode, setFieldBorder, setSelectedFieldId, setWaypoints]
  );

  useSyncTerraDrawMode({ drawMode, mapEngine, setTerraDrawMode });

  const waypointMarkers = useMemo<GooglePointMarker[]>(
    () =>
      waypoints.map((point) => ({
        point,
        title: "Waypoint",
        color: "#1976d2",
      })),
    [waypoints],
  );

  useGooglePointMarkers({
    enabled: terraDrawMode === "static",
    isLoaded: mapRuntime.isLoaded,
    mapReady,
    mapRef,
    markersRef: mapRuntime.waypointMarkersRef,
    markers: waypointMarkers,
  });

  useEffect(() => {
    if (mapEngine !== "google") return;
    if (!mapReady || !selectedField) return;
    loadRingIntoEditor(selectedField.ring);
    focusRingOnMap(selectedField.ring);
  }, [focusRingOnMap, loadRingIntoEditor, mapEngine, mapReady, selectedField]);

  const mapCenter = useMemo(
    () => mapRuntime.droneCenter || mapRuntime.userCenter || mapRuntime.center,
    [mapRuntime.droneCenter, mapRuntime.userCenter, mapRuntime.center],
  );

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
    mapZoom,
    mapCenter,
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
    cesiumFieldBoundary,
    userCenter: mapRuntime.userCenter,
    terraDrawMode,
    setTerraDrawMode,
  };
}
