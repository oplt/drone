import type { LatLng } from "../../../shared/utils/extractLatLng";

export const DEFAULT_MISSION_MAP_CONTAINER_STYLE = {
  width: "100%",
  height: "400px",
} as const;

export const DEFAULT_MISSION_MAP_CENTER: LatLng = {
  lat: 50.8503,
  lng: 4.3517,
};

export const DEFAULT_MISSION_MAP_ZOOM = 12;

export function buildMissionGoogleMapOptions(mapId: string) {
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
}
