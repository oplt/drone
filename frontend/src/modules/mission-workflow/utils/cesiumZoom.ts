import { CESIUM_MAX_SAFE_ZOOM } from "../constants";

export function cesiumZoomForMapZoom(mapZoom: number): number {
  return Math.min(mapZoom, CESIUM_MAX_SAFE_ZOOM);
}
