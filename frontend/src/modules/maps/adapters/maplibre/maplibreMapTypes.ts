import type { Feature, Geometry } from "geojson";
import type { ShapeDrawMode, ShapeDrawResult } from "../../utils/drawingShapes";

export type LatLng = { lat: number; lng: number };
export type Waypoint = { lat: number; lon: number; alt?: number };
export type LonLat = [number, number];
export type SavedFieldBoundary = { id: number; name?: string | null; ring: LonLat[] };
export type FlatDrawMode = ShapeDrawMode;
export type FlatDrawResult = ShapeDrawResult;

export type MapLibreMapProps = {
  center: LatLng;
  zoom: number;
  waypoints?: Waypoint[];
  droneCenter?: LatLng | null;
  userCenter?: LatLng | null;
  onPickLatLng?: (p: LatLng) => void;
  drawMode?: FlatDrawMode;
  onDrawComplete?: (result: FlatDrawResult) => void;
  onBoundaryDrawStarted?: () => void;
  onBoundaryDrawProgress?: (coords: LonLat[]) => void;
  fieldBoundary?: LonLat[] | null;
  savedFields?: SavedFieldBoundary[];
  selectedFieldId?: number | null;
  onSavedFieldClick?: (fieldId: number) => void;
  onFieldBoundaryClick?: () => void;
  drawnBoundarySelected?: boolean;
  plannedRoute?: LonLat[] | null;
  exclusionZones?: LonLat[][];
  height?: number | string;
  focusRing?: LonLat[] | null;
  focusRequestToken?: number;
  followEnabled?: boolean;
  selectedWaypointIndex?: number | null;
  onSelectWaypoint?: (index: number) => void;
};

export const routeSourceId = "mission-route";
export const routeLayerId = "mission-route-line";
export const overlaySourceId = "mission-overlays";
export const overlayFillLayerId = "mission-overlays-fill";
export const overlayLineLayerId = "mission-overlays-line";
export const drawSourceId = "mission-draw-preview";
export const drawPointLayerId = "mission-draw-preview-points";
export const drawLineLayerId = "mission-draw-preview-line";
export const drawFillLayerId = "mission-draw-preview-fill";

export type MapFeature = Feature<
  Geometry,
  { kind?: string; fieldId?: number; selected?: boolean }
>;
