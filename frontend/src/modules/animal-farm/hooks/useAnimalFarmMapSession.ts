import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDroneMapFollow, type CesiumViewMode, type MissionMapEngine } from "../../maps";
import { ANIMAL_FARM_DEFAULT_CENTER } from "../animalFarmPageConstants";
import type { AnimalFarmWaypoint } from "../animalFarmPageTypes";
import type { LatLng } from "../../../shared/utils/extractLatLng";

type UseAnimalFarmMapSessionOptions = {
  waypoints: AnimalFarmWaypoint[];
  droneCenter: LatLng | null;
  userCenter: LatLng | null;
  wsConnected: boolean;
  center: LatLng;
  isLoaded: boolean;
  mapEngine: MissionMapEngine;
  useCesium: boolean;
  cesiumViewMode: CesiumViewMode;
  setCesiumViewMode: (mode: CesiumViewMode) => void;
  handleMapEngineChange: (engine: MissionMapEngine) => void;
};

export function useAnimalFarmMapSession({
  waypoints,
  droneCenter,
  userCenter,
  wsConnected,
  center,
  isLoaded,
  mapEngine,
  useCesium,
  cesiumViewMode,
  setCesiumViewMode,
  handleMapEngineChange,
}: UseAnimalFarmMapSessionOptions) {
  const mapRef = useRef<google.maps.Map | null>(null);
  const [googleMap, setGoogleMap] = useState<google.maps.Map | null>(null);
  const waypointMarkersRef = useRef<
    Array<{ map?: google.maps.Map | null; setMap?: (map: google.maps.Map | null) => void }>
  >([]);
  const [mapReady, setMapReady] = useState(false);
  const [mapZoom, setMapZoom] = useState(12);

  const onMapLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setGoogleMap(map);
    setMapReady(true);
  }, []);

  const onMapZoomChanged = useCallback(() => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (typeof zoom === "number" && Number.isFinite(zoom)) {
      setMapZoom(zoom);
    }
  }, []);

  useDroneMapFollow({
    mapRef,
    droneCenter,
    wsConnected,
    onInitialSnap: () => setMapZoom(18),
  });

  useEffect(() => {
    if (!isLoaded || !mapReady || !mapRef.current) return;

    const markerLib = (
      google.maps as typeof google.maps & {
        marker?: {
          AdvancedMarkerElement?: new (
            options: google.maps.marker.AdvancedMarkerElementOptions,
          ) => google.maps.marker.AdvancedMarkerElement;
        };
      }
    ).marker;
    if (!markerLib?.AdvancedMarkerElement) return;

    waypointMarkersRef.current.forEach((marker) => {
      try {
        if ("map" in marker) marker.map = null;
        else marker.setMap?.(null);
      } catch {
        // ignore cleanup errors
      }
    });
    waypointMarkersRef.current = [];

    if (waypoints.length === 0) return;

    waypoints.forEach((point, idx) => {
      const content = document.createElement("div");
      content.style.width = "26px";
      content.style.height = "26px";
      content.style.borderRadius = "50%";
      content.style.background = "#fff";
      content.style.border = "2px solid #1976d2";
      content.style.color = "#1976d2";
      content.style.display = "flex";
      content.style.alignItems = "center";
      content.style.justifyContent = "center";
      content.style.fontSize = "12px";
      content.style.fontWeight = "600";
      content.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";
      content.textContent = `${idx + 1}`;

      const marker = new markerLib.AdvancedMarkerElement!({
        map: mapRef.current,
        position: { lat: point.lat, lng: point.lon },
        content,
        title: `Waypoint ${idx + 1}`,
      });
      waypointMarkersRef.current.push(marker);
    });

    return () => {
      waypointMarkersRef.current.forEach((marker) => {
        try {
          if ("map" in marker) marker.map = null;
          else marker.setMap?.(null);
        } catch {
          // ignore cleanup errors
        }
      });
      waypointMarkersRef.current = [];
    };
  }, [isLoaded, mapReady, waypoints]);

  const mapCenter = useMemo(() => {
    if (droneCenter) return droneCenter;
    if (waypoints.length > 0) return { lat: waypoints[0].lat, lng: waypoints[0].lon };
    return userCenter || center || ANIMAL_FARM_DEFAULT_CENTER;
  }, [center, droneCenter, userCenter, waypoints]);

  const mapOptions = useMemo(() => {
    const mapId = (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "";
    return {
      streetViewControl: false,
      mapTypeControl: false,
      fullscreenControl: true,
      clickableIcons: false,
      keyboardShortcuts: false,
      gestureHandling: "greedy" as const,
      maxZoom: 20,
      minZoom: 3,
      ...(mapId ? { mapId } : {}),
    };
  }, []);

  return {
    mapRef,
    googleMap,
    mapReady,
    mapZoom,
    useCesium,
    mapEngine,
    cesiumViewMode,
    setCesiumViewMode,
    onMapLoad,
    onMapZoomChanged,
    handleMapEngineChange,
    mapCenter,
    mapOptions,
  };
}
