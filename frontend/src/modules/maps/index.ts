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
export { useMapEngine, dispatchMapEngineChange } from "./hooks/useMapEngine";
export {
  terraDrawToolToShapeMode,
  isFlatDrawToolSelected,
} from "./utils/drawingToolModes";
export { GoogleMapsContext, GoogleMapsProvider } from "./providers/googleMaps";
/** Prefer lazy import via MissionMapViewport; direct use only for tests/tools. */
export { default as CesiumMapLazy } from "./adapters/CesiumMapLazy";
export { default as CesiumMap } from "./adapters/CesiumMap";
export type { DrawResult as CesiumDrawResult } from "./adapters/CesiumMap";
