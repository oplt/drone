import { useEffect, useRef, type MutableRefObject } from "react";
import type { LatLng } from "../../../shared/utils/extractLatLng";

export function useDroneMapFollow({
  mapRef,
  droneCenter,
  wsConnected,
  followEnabled = true,
  onInitialSnap,
}: {
  mapRef: MutableRefObject<google.maps.Map | null>;
  droneCenter: LatLng | null;
  wsConnected: boolean;
  /** When false, operator free-explores without auto pan. */
  followEnabled?: boolean;
  onInitialSnap?: () => void;
}) {
  const snappedToDroneRef = useRef(false);
  const lastPanRef = useRef(0);
  const wasFollowEnabledRef = useRef(followEnabled);

  // Reacquire hard snap when Follow turns back on.
  useEffect(() => {
    if (followEnabled && !wasFollowEnabledRef.current) {
      snappedToDroneRef.current = false;
    }
    wasFollowEnabledRef.current = followEnabled;
  }, [followEnabled]);

  useEffect(() => {
    if (!followEnabled) return;
    if (!mapRef.current || !droneCenter) return;
    if (!snappedToDroneRef.current) {
      snappedToDroneRef.current = true;
      mapRef.current.panTo(droneCenter);
      mapRef.current.setZoom(18);
      onInitialSnap?.();
    }
  }, [mapRef, droneCenter, followEnabled, onInitialSnap]);

  useEffect(() => {
    if (!wsConnected) {
      snappedToDroneRef.current = false;
    }
  }, [wsConnected]);

  useEffect(() => {
    if (!followEnabled) return;
    if (!mapRef.current || !droneCenter || !wsConnected) return;

    const now = Date.now();
    if (now - lastPanRef.current < 500) return;
    lastPanRef.current = now;

    const currentZoom = mapRef.current.getZoom() ?? 0;
    if (currentZoom < 16) return;

    mapRef.current.panTo(droneCenter);
  }, [mapRef, droneCenter, wsConnected, followEnabled]);
}
