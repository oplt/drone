import type * as Cesium from "cesium";
import {
  normalizeLonLatLine,
  normalizeLonLatRing,
} from "../../utils/cesiumCameraGeometry";
import { updateCesiumDroneEntity } from "./cesiumDroneEntity";
import type { DrawMode, LatLng, LonLat, Waypoint } from "./cesiumMapTypes";

type LatestValues = {
  droneCenter: LatLng | null;
  center: LatLng;
  safeHeadingRad: number;
  fieldCameraView: { center: LatLng; topHeight: number } | null;
};

export function syncCesiumSceneEntities(args: {
  CesiumModule: typeof Cesium;
  viewer: Cesium.Viewer;
  drawMode: DrawMode;
  waypoints: Waypoint[];
  fieldBoundary: LonLat[] | null;
  plannedRoute: LonLat[] | null;
  exclusionZones: LonLat[][];
  drawnBoundarySelected: boolean;
  selectedWaypointIndex: number | null;
  planningAltitudeM: number;
  latestValuesRef: { current: LatestValues };
  entityRefs: {
    polylineEntityRef: { current: Cesium.Entity | null };
    waypointPolygonEntityRef: { current: Cesium.Entity | null };
    plannedRouteEntityRef: { current: Cesium.Entity | null };
    fieldBoundaryEntityRef: { current: Cesium.Entity | null };
    exclusionZoneEntityRefs: { current: Cesium.Entity[] };
    waypointEntityRefs: { current: Cesium.Entity[] };
    droneEntityRef: { current: Cesium.Entity | null };
  };
}) {
  const {
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
  } = args;

  const {
    polylineEntityRef,
    waypointPolygonEntityRef,
    plannedRouteEntityRef,
    fieldBoundaryEntityRef,
    exclusionZoneEntityRefs,
    waypointEntityRefs,
    droneEntityRef,
  } = entityRefs;

  if (polylineEntityRef.current) viewer.entities.remove(polylineEntityRef.current);
  if (waypointPolygonEntityRef.current) {
    viewer.entities.remove(waypointPolygonEntityRef.current);
  }
  if (plannedRouteEntityRef.current) {
    viewer.entities.remove(plannedRouteEntityRef.current);
  }
  if (fieldBoundaryEntityRef.current) {
    viewer.entities.remove(fieldBoundaryEntityRef.current);
  }
  exclusionZoneEntityRefs.current.forEach((entity) => viewer.entities.remove(entity));
  exclusionZoneEntityRefs.current = [];
  waypointEntityRefs.current.forEach((entity) => viewer.entities.remove(entity));
  waypointEntityRefs.current = [];

  const wp = waypoints
    .map((waypoint) => ({ lat: waypoint.lat, lng: waypoint.lon }))
    .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));

  const boundaryRing = normalizeLonLatRing(fieldBoundary);
  if (drawMode === "none" && boundaryRing.length >= 3) {
    const boundaryColor = drawnBoundarySelected ? "#1976d2" : "#1565c0";
    const boundaryPositions = CesiumModule.Cartesian3.fromDegreesArray(
      boundaryRing.flatMap(([lng, lat]) => [lng, lat]),
    );
    fieldBoundaryEntityRef.current = viewer.entities.add({
      polygon: {
        hierarchy: new CesiumModule.PolygonHierarchy(boundaryPositions),
        material: CesiumModule.Color.fromCssColorString(boundaryColor).withAlpha(
          drawnBoundarySelected ? 0.22 : 0.15,
        ),
        outline: true,
        outlineColor: CesiumModule.Color.fromCssColorString(boundaryColor),
        perPositionHeight: false,
      },
    });
  } else {
    fieldBoundaryEntityRef.current = null;
  }

  for (const zone of exclusionZones) {
    const ring = normalizeLonLatRing(zone);
    if (ring.length < 3) continue;
    const positions = CesiumModule.Cartesian3.fromDegreesArray(
      ring.flatMap(([lng, lat]) => [lng, lat]),
    );
    const entity = viewer.entities.add({
      polygon: {
        hierarchy: new CesiumModule.PolygonHierarchy(positions),
        material: CesiumModule.Color.fromCssColorString("#d32f2f").withAlpha(0.28),
        outline: true,
        outlineColor: CesiumModule.Color.fromCssColorString("#b71c1c"),
        perPositionHeight: false,
      },
    });
    exclusionZoneEntityRefs.current.push(entity);
  }

  const routeLine = normalizeLonLatLine(plannedRoute);
  if (routeLine.length >= 2) {
    const routePositions = CesiumModule.Cartesian3.fromDegreesArray(
      routeLine.flatMap(([lng, lat]) => [lng, lat]),
    );
    plannedRouteEntityRef.current = viewer.entities.add({
      polyline: {
        positions: routePositions,
        width: 4,
        material: CesiumModule.Color.fromCssColorString("#2e7d32"),
        clampToGround: true,
      },
    });
  } else {
    plannedRouteEntityRef.current = null;
  }

  wp.forEach((point, index) => {
    const selected = selectedWaypointIndex === index;
    const entity = viewer.entities.add({
      position: CesiumModule.Cartesian3.fromDegrees(point.lng, point.lat),
      point: {
        pixelSize: selected ? 16 : 10,
        color: CesiumModule.Color.fromCssColorString(selected ? "#ff6d00" : "#1976d2"),
        outlineColor: CesiumModule.Color.WHITE,
        outlineWidth: selected ? 2 : 1,
      },
      properties: { waypointIndex: index },
    });
    waypointEntityRefs.current.push(entity);
  });

  if (wp.length >= 2 && routeLine.length < 2) {
    const positions = wp.flatMap((point) => [point.lng, point.lat]);
    polylineEntityRef.current = viewer.entities.add({
      polyline: {
        positions: CesiumModule.Cartesian3.fromDegreesArray(positions),
        width: 3,
        clampToGround: true,
      },
    });
  } else {
    polylineEntityRef.current = null;
  }

  if (wp.length >= 3 && routeLine.length < 2) {
    const positions = CesiumModule.Cartesian3.fromDegreesArray(
      wp.flatMap((point) => [point.lng, point.lat]),
    );
    waypointPolygonEntityRef.current = viewer.entities.add({
      polygon: {
        hierarchy: new CesiumModule.PolygonHierarchy(positions),
        material: CesiumModule.Color.fromCssColorString("#1976d2").withAlpha(0.14),
        outline: true,
        outlineColor: CesiumModule.Color.fromCssColorString("#1976d2"),
        perPositionHeight: false,
      },
    });
  } else {
    waypointPolygonEntityRef.current = null;
  }

  updateCesiumDroneEntity({
    CesiumModule,
    viewer,
    droneEntityRef,
    latestValues: latestValuesRef.current,
    planningAltitudeM,
  });
}
