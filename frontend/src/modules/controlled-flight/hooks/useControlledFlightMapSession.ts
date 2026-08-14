import { useCallback, useMemo, useRef, useState } from "react";
import { useDroneMapFollow } from "../../maps";
import { CONTROLLED_FLIGHT_DEFAULT_CENTER } from "../controlledFlightViewConstants";
import type { LatLng } from "../../../shared/utils/extractLatLng";

type UseControlledFlightMapSessionOptions = {
  droneCenter: LatLng | null;
  userCenter: LatLng | null;
  wsConnected: boolean;
  mapId: string;
};

export function useControlledFlightMapSession({
  droneCenter,
  userCenter,
  wsConnected,
  mapId,
}: UseControlledFlightMapSessionOptions) {
  const mapRef = useRef<google.maps.Map | null>(null);
  const [googleMap, setGoogleMap] = useState<google.maps.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapZoom, setMapZoom] = useState(12);
  const [center, setCenter] = useState<LatLng>(CONTROLLED_FLIGHT_DEFAULT_CENTER);
  const lastSyncedCenterRef = useRef<LatLng | null>(null);

  const onMapLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setGoogleMap(map);
    setMapReady(true);
  }, []);

  const onMapUnmount = useCallback(() => {
    mapRef.current = null;
    setGoogleMap(null);
    setMapReady(false);
  }, []);

  const onMapZoomChanged = useCallback(() => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (typeof zoom === "number" && Number.isFinite(zoom)) {
      setMapZoom(zoom);
    }
  }, []);

  const onMapCenterChanged = useCallback(() => {
    if (!mapRef.current) return;
    const nextCenter = mapRef.current.getCenter();
    if (!nextCenter) return;
    const newCenter = { lat: nextCenter.lat(), lng: nextCenter.lng() };
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

  const mapCenter = useMemo(
    () => droneCenter || userCenter || center,
    [center, droneCenter, userCenter],
  );

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
    [mapId],
  );

  return {
    mapRef,
    googleMap,
    mapReady,
    mapZoom,
    mapCenter,
    mapOptions,
    onMapLoad,
    onMapUnmount,
    onMapZoomChanged,
    onMapCenterChanged,
  };
}
