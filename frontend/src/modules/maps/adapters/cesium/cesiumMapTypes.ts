import type { ShapeDrawMode, ShapeDrawResult } from "../../utils/drawingShapes";

export type LatLng = { lat: number; lng: number };
export type Waypoint = { lat: number; lon: number; alt: number };
export type LonLat = [number, number];
export type CesiumViewMode = "top" | "tilted" | "follow" | "fpv" | "orbit";
export type DrawMode = ShapeDrawMode;
export type DrawResult = ShapeDrawResult;

export type CesiumMapProps = {
  center: LatLng;
  zoom: number;
  viewMode: CesiumViewMode;
  waypoints: Waypoint[];
  droneCenter: LatLng | null;
  headingDeg?: number | null;
  onPickLatLng?: (p: LatLng) => void;
  drawMode?: DrawMode;
  onDrawComplete?: (res: DrawResult) => void;
  onBoundaryDrawStarted?: () => void;
  onBoundaryDrawProgress?: (coords: LonLat[]) => void;
  fieldBoundary?: LonLat[] | null;
  onFieldBoundaryClick?: () => void;
  drawnBoundarySelected?: boolean;
  plannedRoute?: LonLat[] | null;
  exclusionZones?: LonLat[][];
  fieldTilesetUrl?: string | null;
  planningAltitudeM?: number;
  lockCameraToPlanningAltitude?: boolean;
  useWorldTerrain?: boolean;
  focusRing?: LonLat[] | null;
  focusRequestToken?: number;
  followEnabled?: boolean;
  selectedWaypointIndex?: number | null;
  onSelectWaypoint?: (index: number) => void;
};

export const EMPTY_EXCLUSION_ZONES: LonLat[][] = [];
