import type * as Cesium from "cesium";

export function pickCartesianOnGlobe(
  viewer: Cesium.Viewer,
  CesiumModule: typeof Cesium,
  screenPos: Cesium.Cartesian2,
): Cesium.Cartesian3 | null {
  const scene = viewer.scene;

  if (scene.pickPositionSupported && scene.pickPosition) {
    const picked = scene.pickPosition(screenPos);
    if (CesiumModule.defined(picked)) return picked;
  }

  const ray = viewer.camera.getPickRay(screenPos);
  if (!ray) return null;

  const picked = scene.globe.pick(ray, scene);
  return picked ?? null;
}

export function cartesianToLngLat(
  CesiumModule: typeof Cesium,
  cartesian: Cesium.Cartesian3,
): LonLatTuple {
  const carto = CesiumModule.Cartographic.fromCartesian(cartesian);
  return [
    CesiumModule.Math.toDegrees(carto.longitude),
    CesiumModule.Math.toDegrees(carto.latitude),
  ];
}

type LonLatTuple = [number, number];
