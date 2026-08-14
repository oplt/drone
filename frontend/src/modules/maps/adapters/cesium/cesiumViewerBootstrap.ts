import type * as Cesium from "cesium";
import { zoomToHeightMeters } from "../../utils/cesiumCameraGeometry";
import { applyCesiumCameraMode } from "./cesiumCameraMode";
import { updateCesiumDroneEntity } from "./cesiumDroneEntity";
import { loadCesiumFieldTileset } from "./cesiumFieldTileset";
import { syncCesiumSceneEntities } from "./cesiumSceneEntities";
import type {
  CesiumViewMode,
  DrawMode,
  LatLng,
  LonLat,
  Waypoint,
} from "./cesiumMapTypes";

type CesiumLatestValues = {
  droneCenter: LatLng | null;
  center: LatLng;
  safeHeadingRad: number;
  fieldCameraView: { center: LatLng; topHeight: number } | null;
};

export type CesiumBootstrapContextRefs = {
  cesiumRef: { current: typeof Cesium | null };
  viewerRef: { current: Cesium.Viewer | null };
  clickHandlerRef: { current: Cesium.ScreenSpaceEventHandler | null };
  viewerReadyRef: { current: boolean };
  drawModeRef: { current: DrawMode };
  onSelectWaypointRef: {
    current: ((index: number) => void) | undefined;
  };
  onPickLatLngRef: { current: ((point: LatLng) => void) | undefined };
  onFieldBoundaryClickRef: { current: (() => void) | undefined };
  latestValuesRef: { current: CesiumLatestValues };
  entityRefs: {
    polylineEntityRef: { current: Cesium.Entity | null };
    waypointPolygonEntityRef: { current: Cesium.Entity | null };
    plannedRouteEntityRef: { current: Cesium.Entity | null };
    fieldBoundaryEntityRef: { current: Cesium.Entity | null };
    exclusionZoneEntityRefs: { current: Cesium.Entity[] };
    waypointEntityRefs: { current: Cesium.Entity[] };
    droneEntityRef: { current: Cesium.Entity | null };
  };
  fieldTilesetRef: { current: Cesium.Cesium3DTileset | null };
  tilesetLoadSeqRef: { current: number };
  userInteractingRef: { current: boolean };
  lastCameraSignatureRef: { current: string | null };
  rafRef: { current: number | null };
};

export type BootstrapCesiumViewerArgs = {
  hostElement: HTMLDivElement;
  isCancelled: () => boolean;
  useWorldTerrain: boolean;
  refs: CesiumBootstrapContextRefs;
  drawMode: DrawMode;
  waypoints: Waypoint[];
  fieldBoundary: LonLat[] | null;
  plannedRoute: LonLat[] | null;
  exclusionZones: LonLat[][];
  drawnBoundarySelected: boolean;
  selectedWaypointIndex: number | null;
  planningAltitudeM: number;
  fieldTilesetUrl: string | null;
  viewMode: CesiumViewMode;
  zoom: number;
  followEnabled: boolean;
  lockCameraToPlanningAltitude: boolean;
  fieldCameraView: { center: LatLng; topHeight: number } | null;
  droneCenter: LatLng | null;
  center: LatLng;
};

export async function bootstrapCesiumViewer(
  args: BootstrapCesiumViewerArgs,
): Promise<{ cancelled: boolean }> {
  const {
    hostElement,
    isCancelled,
    useWorldTerrain,
    refs,
    drawMode,
    waypoints,
    fieldBoundary,
    plannedRoute,
    exclusionZones,
    drawnBoundarySelected,
    selectedWaypointIndex,
    planningAltitudeM,
    fieldTilesetUrl,
    viewMode,
    zoom,
    followEnabled,
    lockCameraToPlanningAltitude,
    fieldCameraView,
    droneCenter,
    center,
  } = args;

  const {
    cesiumRef,
    viewerRef,
    clickHandlerRef,
    viewerReadyRef,
    drawModeRef,
    onSelectWaypointRef,
    onPickLatLngRef,
    onFieldBoundaryClickRef,
    latestValuesRef,
    entityRefs,
    fieldTilesetRef,
    tilesetLoadSeqRef,
    userInteractingRef,
    lastCameraSignatureRef,
    rafRef,
  } = refs;

  const CesiumModule = await import("cesium");
  if (isCancelled()) return { cancelled: true };

  const token = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;
  if (token) CesiumModule.Ion.defaultAccessToken = token;

  cesiumRef.current = CesiumModule;

  const viewer = new CesiumModule.Viewer(hostElement, {
    animation: false,
    timeline: false,
    geocoder: false,
    baseLayerPicker: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: false,
    selectionIndicator: false,
    fullscreenButton: false,
    shouldAnimate: true,
  });

  viewer.scene.globe.depthTestAgainstTerrain = false;

  if (useWorldTerrain) {
    try {
      if (CesiumModule.createWorldTerrainAsync) {
        viewer.terrainProvider = await CesiumModule.createWorldTerrainAsync();
      } else if (
        typeof (CesiumModule as typeof Cesium & { createWorldTerrain?: () => Cesium.TerrainProvider })
          .createWorldTerrain === "function"
      ) {
        viewer.terrainProvider = (
          CesiumModule as typeof Cesium & {
            createWorldTerrain: () => Cesium.TerrainProvider;
          }
        ).createWorldTerrain();
      }
    } catch {
      // keep default terrain
    }
  }

  if (isCancelled()) {
    try {
      viewer.destroy();
    } catch {
      // ignore cleanup errors
    }
    return { cancelled: true };
  }

  viewerRef.current = viewer;

  const handler = new CesiumModule.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((movement: { position: Cesium.Cartesian2 }) => {
    if (drawModeRef.current !== "none") return;

    const picked = viewer.scene.pick(movement.position);
    if (picked?.id) {
      const rawIndex = picked.id.properties?.waypointIndex;
      const waypointIndex =
        typeof rawIndex === "number"
          ? rawIndex
          : rawIndex?.getValue?.(CesiumModule.JulianDate.now());
      if (typeof waypointIndex === "number") {
        onSelectWaypointRef.current?.(waypointIndex);
        return;
      }
      if (picked.id === entityRefs.fieldBoundaryEntityRef.current) {
        onFieldBoundaryClickRef.current?.();
        return;
      }
    }

    if (!onPickLatLngRef.current) return;
    const scene = viewer.scene;
    let cartesian: Cesium.Cartesian3 | null =
      scene.pickPosition?.(movement.position) ?? null;
    if (!cartesian) {
      cartesian =
        viewer.camera.pickEllipsoid(
          movement.position,
          scene.globe.ellipsoid,
        ) ?? null;
    }
    if (!cartesian) return;

    const carto = CesiumModule.Cartographic.fromCartesian(cartesian);
    const lat = CesiumModule.Math.toDegrees(carto.latitude);
    const lng = CesiumModule.Math.toDegrees(carto.longitude);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      onPickLatLngRef.current({ lat, lng });
    }
  }, CesiumModule.ScreenSpaceEventType.LEFT_CLICK);
  clickHandlerRef.current = handler;

  const initialTarget = fieldCameraView?.center ?? droneCenter ?? center;
  const initialHeight = fieldCameraView?.topHeight ?? zoomToHeightMeters(zoom);
  viewer.camera.setView({
    destination: CesiumModule.Cartesian3.fromDegrees(
      initialTarget.lng,
      initialTarget.lat,
      initialHeight,
    ),
  });

  viewerReadyRef.current = true;

  syncCesiumSceneEntities({
    CesiumModule,
    viewer,
    drawMode,
    waypoints,
    fieldBoundary,
    plannedRoute,
    exclusionZones,
    drawnBoundarySelected,
    selectedWaypointIndex,
    planningAltitudeM,
    latestValuesRef,
    entityRefs,
  });

  updateCesiumDroneEntity({
    CesiumModule,
    viewer,
    droneEntityRef: entityRefs.droneEntityRef,
    latestValues: latestValuesRef.current,
    planningAltitudeM,
  });

  void loadCesiumFieldTileset({
    CesiumModule,
    viewer,
    url: fieldTilesetUrl,
    fieldTilesetRef,
    tilesetLoadSeqRef,
    viewerRef,
  });

  applyCesiumCameraMode({
    CesiumModule,
    viewer,
    viewMode,
    zoom,
    followEnabled,
    planningAltitudeM,
    lockCameraToPlanningAltitude,
    latestValuesRef,
    droneEntityRef: entityRefs.droneEntityRef,
    userInteractingRef,
    lastCameraSignatureRef,
    rafRef,
  });

  return { cancelled: false };
}
