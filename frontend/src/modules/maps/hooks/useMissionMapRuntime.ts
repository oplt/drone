import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useMissionCommandMetrics } from "../../mission-runtime";
import { type LatLng } from "../../../shared/utils/extractLatLng";
import { GoogleMapsContext } from "../providers/googleMaps";
import { useDroneCenter } from "./useDroneCenter";
import { useDroneMapFollow } from "./useDroneMapFollow";
import { useUserLocation } from "./useUserLocation";
import { useMissionVideoStreamState } from "./useMissionVideoStreamState";
import {
  buildMissionGoogleMapOptions,
  DEFAULT_MISSION_MAP_CENTER,
  DEFAULT_MISSION_MAP_CONTAINER_STYLE,
  DEFAULT_MISSION_MAP_ZOOM,
} from "../config/missionMapDefaults";
import type { CesiumViewMode, MissionMapEngine } from "../types";

export function useMissionMapRuntime({
  apiBase,
  wsConnected,
  droneConnected,
  telemetry,
  activeFlightId,
  fieldTilesetUrl,
  controlledMapEngine,
  onMapEngineChange,
  fieldPolygonRef,
  onAutoStartVideoError,
  onLocationError,
}: {
  apiBase: string;
  wsConnected: boolean;
  droneConnected: boolean;
  telemetry: unknown;
  activeFlightId: string | null;
  fieldTilesetUrl: string | null | undefined;
  controlledMapEngine: MissionMapEngine;
  onMapEngineChange: (engine: MissionMapEngine) => void;
  fieldPolygonRef: React.MutableRefObject<google.maps.Polygon | null>;
  onAutoStartVideoError: (message: string) => void;
  onLocationError: (error: GeolocationPositionError) => string;
}) {
  const mapRef = useRef<google.maps.Map | null>(null);
  const waypointMarkersRef = useRef<unknown[]>([]);
  const lastSyncedCenterRef = useRef<LatLng | null>(null);
  const [terraDrawReady, setTerraDrawReady] = useState(false);
  const [center, setCenter] = useState(DEFAULT_MISSION_MAP_CENTER);
  const [mapZoom, setMapZoom] = useState(DEFAULT_MISSION_MAP_ZOOM);
  const [mapReady, setMapReady] = useState(false);
  const [cesiumViewMode, setCesiumViewMode] = useState<CesiumViewMode>("tilted");
  const mapEngine = controlledMapEngine;

  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string;
  const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";

  const { isLoaded, loadError } = useContext(GoogleMapsContext);
  const droneCenter = useDroneCenter(telemetry);
  const { heading, armed } = useMissionCommandMetrics(telemetry);
  const droneReady = Boolean(droneConnected);

  const videoStream = useMissionVideoStreamState({
    apiBase,
    activeFlightId,
    droneReady,
    droneConnected,
    onAutoStartVideoError,
  });

  const handleMapEngineChange = useCallback(
    (next: MissionMapEngine) => {
      onMapEngineChange(next);
    },
    [onMapEngineChange],
  );

  useEffect(() => {
    if (!fieldTilesetUrl) return;
    handleMapEngineChange("cesium");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCesiumViewMode("top");
  }, [fieldTilesetUrl, handleMapEngineChange]);

  const { userCenter, loadingLocation } = useUserLocation({
    onLocationError,
  });

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

  const mapOptions = useMemo(() => buildMissionGoogleMapOptions(mapId), [mapId]);

  return {
    containerStyle: DEFAULT_MISSION_MAP_CONTAINER_STYLE,
    mapRef,
    waypointMarkersRef,
    lastSyncedCenterRef,
    terraDrawReady,
    setTerraDrawReady,
    center,
    setCenter,
    mapZoom,
    setMapZoom,
    mapReady,
    mapEngine,
    handleMapEngineChange,
    cesiumViewMode,
    setCesiumViewMode,
    mapOptions,
    loadingLocation,
    isLoaded,
    loadError,
    apiKey,
    mapId,
    streamKey: videoStream.streamKey,
    setStreamKey: videoStream.setStreamKey,
    videoToken: videoStream.videoToken,
    startingVideo: videoStream.startingVideo,
    videoError: videoStream.videoError,
    videoRetryCount: videoStream.videoRetryCount,
    droneCenter,
    heading,
    armed,
    userCenter,
    onMapLoad,
    onMapUnmount,
    onMapZoomChanged,
    onMapCenterChanged,
    handleVideoError: videoStream.handleVideoError,
    handleVideoLoad: videoStream.handleVideoLoad,
    handleVideoRetry: videoStream.handleVideoRetry,
  };
}
