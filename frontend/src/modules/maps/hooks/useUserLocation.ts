import { useCallback, useEffect, useRef, useState } from "react";

import type { LatLng } from "../../../shared/utils/extractLatLng";

const GEOLOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  timeout: 5000,
  maximumAge: 0,
};

const UNSUPPORTED_MESSAGE = "Geolocation is not supported by this browser.";

export type UserLocationErrorPolicy = (error: GeolocationPositionError) => string | null;

export interface UseUserLocationOptions {
  onLocationError?: UserLocationErrorPolicy;
}

export interface UserLocationResult {
  userCenter: LatLng | null;
  loadingLocation: boolean;
  requestLocation: () => void;
  locationError: string | null;
}

export function useUserLocation({
  onLocationError,
}: UseUserLocationOptions = {}): UserLocationResult {
  const geolocationSupported = Boolean(navigator.geolocation);
  const [userCenter, setUserCenter] = useState<LatLng | null>(null);
  const [loadingLocation, setLoadingLocation] = useState(geolocationSupported);
  const [locationError, setLocationError] = useState<string | null>(
    geolocationSupported ? null : UNSUPPORTED_MESSAGE,
  );
  const requestedRef = useRef(false);
  const mountedRef = useRef(true);

  const requestLocation = useCallback(() => {
    if (requestedRef.current) return;
    requestedRef.current = true;

    if (!navigator.geolocation) {
      console.warn(UNSUPPORTED_MESSAGE);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!mountedRef.current) return;
        setUserCenter({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setLocationError(null);
        setLoadingLocation(false);
      },
      (error) => {
        if (!mountedRef.current) return;
        const message = onLocationError?.(error) ?? error.message;
        setLocationError(message);
        setLoadingLocation(false);
      },
      GEOLOCATION_OPTIONS,
    );
  }, [onLocationError]);

  useEffect(() => {
    mountedRef.current = true;
    requestLocation();
    return () => {
      mountedRef.current = false;
    };
  }, [requestLocation]);

  return { userCenter, loadingLocation, requestLocation, locationError };
}
