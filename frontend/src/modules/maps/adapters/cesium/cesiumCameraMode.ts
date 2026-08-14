import type * as Cesium from "cesium";
import { clamp, zoomToHeightMeters } from "../../utils/cesiumCameraGeometry";
import type { CesiumViewMode, LatLng } from "./cesiumMapTypes";

type LatestValues = {
  droneCenter: LatLng | null;
  center: LatLng;
  safeHeadingRad: number;
  fieldCameraView: { center: LatLng; topHeight: number } | null;
};

export function applyCesiumCameraMode(args: {
  CesiumModule: typeof Cesium;
  viewer: Cesium.Viewer;
  viewMode: CesiumViewMode;
  zoom: number;
  followEnabled: boolean;
  planningAltitudeM: number;
  lockCameraToPlanningAltitude: boolean;
  latestValuesRef: { current: LatestValues };
  droneEntityRef: { current: Cesium.Entity | null };
  userInteractingRef: { current: boolean };
  lastCameraSignatureRef: { current: string | null };
  rafRef: { current: number | null };
}) {
  const {
    CesiumModule,
    viewer,
    viewMode,
    zoom,
    followEnabled,
    planningAltitudeM,
    lockCameraToPlanningAltitude,
    latestValuesRef,
    droneEntityRef,
    userInteractingRef,
    lastCameraSignatureRef,
    rafRef,
  } = args;

  if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
  rafRef.current = null;

  viewer.trackedEntity = undefined;

  const {
    droneCenter: dc,
    center: c,
    safeHeadingRad: headingRad,
    fieldCameraView: fieldView,
  } = latestValuesRef.current;
  const planningHeight = clamp(
    Number.isFinite(planningAltitudeM) ? planningAltitudeM : 25,
    20,
    30,
  );
  const defaultBaseHeight = lockCameraToPlanningAltitude
    ? planningHeight
    : zoomToHeightMeters(zoom);
  const baseHeight =
    !lockCameraToPlanningAltitude && !dc && fieldView
      ? fieldView.topHeight
      : defaultBaseHeight;
  const tiltedHeight = lockCameraToPlanningAltitude
    ? clamp(baseHeight + 5, 20, 30)
    : Math.max(500, Math.round(baseHeight * 0.6));
  const followHeight = lockCameraToPlanningAltitude
    ? clamp(baseHeight + 4, 20, 30)
    : Math.max(300, Math.round(baseHeight * 0.4));
  const overviewTarget = fieldView?.center ?? c;
  const target =
    viewMode === "follow" || viewMode === "fpv" || viewMode === "orbit"
      ? (dc ?? overviewTarget)
      : overviewTarget;

  const setView = (opts: {
    lat: number;
    lng: number;
    height: number;
    headingRad?: number;
    pitchRad?: number;
    rollRad?: number;
    fly?: boolean;
    signature?: string;
  }) => {
    if (opts.signature && lastCameraSignatureRef.current === opts.signature) {
      return;
    }
    if (opts.signature) {
      lastCameraSignatureRef.current = opts.signature;
    }
    const destination = CesiumModule.Cartesian3.fromDegrees(
      opts.lng,
      opts.lat,
      opts.height,
    );
    const orientation = {
      heading: opts.headingRad ?? 0,
      pitch: opts.pitchRad ?? CesiumModule.Math.toRadians(-60),
      roll: opts.rollRad ?? 0,
    };
    if (opts.fly) {
      viewer.camera.flyTo({ destination, orientation, duration: 0.6 });
    } else {
      viewer.camera.setView({ destination, orientation });
    }
  };

  if (viewMode === "top") {
    const signature = [
      viewMode,
      target.lat.toFixed(7),
      target.lng.toFixed(7),
      Math.round(baseHeight),
      fieldView ? "field" : "center",
    ].join(":");
    setView({
      lat: target.lat,
      lng: target.lng,
      height: baseHeight,
      headingRad: 0,
      pitchRad: CesiumModule.Math.toRadians(-90),
      fly: true,
      signature,
    });
    return;
  }

  if (viewMode === "tilted") {
    const signature = [
      viewMode,
      target.lat.toFixed(7),
      target.lng.toFixed(7),
      Math.round(tiltedHeight),
      fieldView ? "field" : "center",
    ].join(":");
    setView({
      lat: target.lat,
      lng: target.lng,
      height: tiltedHeight,
      headingRad: 0,
      pitchRad: CesiumModule.Math.toRadians(-45),
      fly: true,
      signature,
    });
    return;
  }

  if (viewMode === "follow") {
    if (!followEnabled) {
      viewer.trackedEntity = undefined;
      return;
    }
    lastCameraSignatureRef.current = null;
    if (droneEntityRef.current) {
      viewer.trackedEntity = droneEntityRef.current;
      setView({
        lat: target.lat,
        lng: target.lng,
        height: followHeight,
        headingRad,
        pitchRad: CesiumModule.Math.toRadians(-35),
        fly: true,
      });
    } else {
      setView({
        lat: c.lat,
        lng: c.lng,
        height: tiltedHeight,
        headingRad: 0,
        pitchRad: CesiumModule.Math.toRadians(-45),
        fly: true,
      });
    }
    return;
  }

  const getCurrentCameraHeight = (): number => {
    if (lockCameraToPlanningAltitude) return baseHeight;
    try {
      const camCarto = CesiumModule.Cartographic.fromCartesian(viewer.camera.position);
      const height = camCarto.height;
      return Number.isFinite(height) && height > 0 ? height : baseHeight;
    } catch {
      return baseHeight;
    }
  };

  const tickFPV = () => {
    if (!userInteractingRef.current) {
      const {
        droneCenter: p0,
        center: p1,
        safeHeadingRad: hr,
        fieldCameraView: fv,
      } = latestValuesRef.current;
      const p = p0 ?? fv?.center ?? p1;

      const currentHeight = lockCameraToPlanningAltitude
        ? baseHeight
        : Math.max(5, getCurrentCameraHeight());
      const currentPitch = viewer.camera.pitch;

      setView({
        lat: p.lat,
        lng: p.lng,
        height: currentHeight,
        headingRad: hr,
        pitchRad: currentPitch,
        rollRad: 0,
        fly: false,
      });
    }
    rafRef.current = requestAnimationFrame(tickFPV);
  };

  const tickOrbit = () => {
    if (!userInteractingRef.current) {
      const {
        droneCenter: p0,
        center: p1,
        fieldCameraView: fv,
      } = latestValuesRef.current;
      const p = p0 ?? fv?.center ?? p1;
      const t = performance.now() * 0.00015;
      const radiusMeters = lockCameraToPlanningAltitude ? 35 : 250;

      const heightMeters = lockCameraToPlanningAltitude
        ? baseHeight
        : Math.max(50, getCurrentCameraHeight());

      const dLat = (radiusMeters * Math.cos(t)) / 111_320;
      const dLng =
        (radiusMeters * Math.sin(t)) / (111_320 * Math.cos((p.lat * Math.PI) / 180));
      const camLat = p.lat + dLat;
      const camLng = p.lng + dLng;
      const heading = Math.atan2(p.lng - camLng, p.lat - camLat);
      setView({
        lat: camLat,
        lng: camLng,
        height: heightMeters,
        headingRad: heading,
        pitchRad: CesiumModule.Math.toRadians(-25),
        rollRad: 0,
        fly: false,
      });
    }
    rafRef.current = requestAnimationFrame(tickOrbit);
  };

  if (viewMode === "fpv") {
    if (!followEnabled) {
      viewer.trackedEntity = undefined;
      return;
    }
    lastCameraSignatureRef.current = null;
    tickFPV();
    return;
  }
  if (viewMode === "orbit") {
    if (!followEnabled) {
      viewer.trackedEntity = undefined;
      return;
    }
    lastCameraSignatureRef.current = null;
    tickOrbit();
  }
}
