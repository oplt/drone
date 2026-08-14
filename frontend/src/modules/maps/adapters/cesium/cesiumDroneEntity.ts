import type * as Cesium from "cesium";
import droneIconUrl from "../../../../assets/Drone.svg?url";
import { clamp } from "../../utils/cesiumCameraGeometry";
import type { LatLng } from "./cesiumMapTypes";

type LatestValues = {
  droneCenter: LatLng | null;
  center: LatLng;
  safeHeadingRad: number;
  fieldCameraView: { center: LatLng; topHeight: number } | null;
};

export function updateCesiumDroneEntity(args: {
  CesiumModule: typeof Cesium;
  viewer: Cesium.Viewer;
  droneEntityRef: { current: Cesium.Entity | null };
  latestValues: LatestValues;
  planningAltitudeM: number;
}) {
  const { CesiumModule, viewer, droneEntityRef, latestValues, planningAltitudeM } =
    args;
  const dc = latestValues.droneCenter;
  if (!dc) {
    if (droneEntityRef.current) {
      viewer.entities.remove(droneEntityRef.current);
      droneEntityRef.current = null;
    }
    return;
  }

  const markerHeightM = clamp(
    Number.isFinite(planningAltitudeM) ? planningAltitudeM : 25,
    10,
    120,
  );
  const position = CesiumModule.Cartesian3.fromDegrees(
    dc.lng,
    dc.lat,
    markerHeightM,
  );
  if (!droneEntityRef.current) {
    droneEntityRef.current = viewer.entities.add({
      position,
      billboard: {
        image: droneIconUrl,
        width: 40,
        height: 40,
        rotation: latestValues.safeHeadingRad,
        alignedAxis: CesiumModule.Cartesian3.UNIT_Z,
        verticalOrigin: CesiumModule.VerticalOrigin.CENTER,
        horizontalOrigin: CesiumModule.HorizontalOrigin.CENTER,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: "DRONE",
        pixelOffset: new CesiumModule.Cartesian2(0, -22),
        scale: 0.85,
        showBackground: true,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    return;
  }

  droneEntityRef.current.position = new CesiumModule.ConstantPositionProperty(
    position,
  );
  if (droneEntityRef.current.billboard) {
    droneEntityRef.current.billboard.rotation = new CesiumModule.ConstantProperty(
      latestValues.safeHeadingRad,
    );
  }
}
