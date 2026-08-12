/**
 * Maps capability module. CesiumMap lives in adapters/ as a temporary boundary
 * (pre-split monolith); consumers must import engines only through MissionMapViewport.
 */
export * from "./types";
export {
  DEFAULT_MISSION_MAP_ENGINE,
  MissionMapViewport,
} from "./components/MissionMapViewport";
export { TerraDrawController } from "./components/TerraDrawController";
export { RouteDrawControls } from "./components/RouteDrawControls";
export { CesiumViewControls } from "./components/CesiumViewControls";
export { useDroneMapFollow } from "./hooks/useDroneMapFollow";
export { useDroneCenter } from "./hooks/useDroneCenter";
export {
  useUserLocation,
  type UserLocationErrorPolicy,
  type UserLocationResult,
  type UseUserLocationOptions,
} from "./hooks/useUserLocation";
export { useMapEngine, dispatchMapEngineChange } from "./hooks/useMapEngine";
export {
  terraDrawToolToShapeMode,
  isFlatDrawToolSelected,
} from "./utils/drawingToolModes";
export { GoogleMapsContext, GoogleMapsProvider } from "./providers/googleMaps";
/** Engine implementation is available only through the lazy boundary. */
export { default as CesiumMapLazy } from "./adapters/CesiumMapLazy";
export type { DrawResult as CesiumDrawResult } from "./adapters/CesiumMap";
