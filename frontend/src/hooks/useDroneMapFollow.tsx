import { useEffect, useRef, type MutableRefObject } from "react";
import type { LatLng } from "../lib/extractLatLng";

export function useDroneMapFollow({
  mapRef,
  droneCenter,
  wsConnected,
  onInitialSnap,
}: {
  mapRef: MutableRefObject<google.maps.Map | null>;
  droneCenter: LatLng | null;
  wsConnected: boolean;
  onInitialSnap?: () => void;
}) {
  const snappedToDroneRef = useRef(false);
  const lastPanRef = useRef(0);

  useEffect(() => {
    if (!mapRef.current || !droneCenter) return;
    if (!snappedToDroneRef.current) {
      snappedToDroneRef.current = true;
      mapRef.current.panTo(droneCenter);
      mapRef.current.setZoom(18);
      onInitialSnap?.();
    }
  }, [mapRef, droneCenter, onInitialSnap]);

  useEffect(() => {
    if (!wsConnected) {
      snappedToDroneRef.current = false;
    }
  }, [wsConnected]);

  useEffect(() => {
    if (!mapRef.current || !droneCenter || !wsConnected) return;

    const now = Date.now();
    if (now - lastPanRef.current < 500) return;
    lastPanRef.current = now;

    const currentZoom = mapRef.current.getZoom() ?? 0;
    if (currentZoom < 16) return;

    mapRef.current.panTo(droneCenter);
  }, [mapRef, droneCenter, wsConnected]);
}
