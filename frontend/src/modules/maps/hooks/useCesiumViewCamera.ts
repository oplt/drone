import { useEffect } from "react";
import { computeFieldCameraView } from "../utils/cesiumCameraGeometry";
import { applyCesiumCameraMode } from "../adapters/cesium/cesiumCameraMode";
import type { CesiumMapProps } from "../adapters/cesium/cesiumMapTypes";
import type { CesiumMapRefs } from "./useCesiumMapRefs";

type UseCesiumViewCameraArgs = {
  refs: CesiumMapRefs;
  props: Pick<
    CesiumMapProps,
    | "viewMode"
    | "zoom"
    | "followEnabled"
    | "planningAltitudeM"
    | "lockCameraToPlanningAltitude"
    | "selectedWaypointIndex"
    | "waypoints"
    | "fieldBoundary"
    | "focusRing"
    | "focusRequestToken"
  >;
  cameraCenterKey: string;
  hasDroneCenter: boolean;
  fieldCameraView: { center: { lat: number; lng: number }; topHeight: number } | null;
};

export function useCesiumViewCamera({
  refs,
  props,
  cameraCenterKey,
  hasDroneCenter,
  fieldCameraView,
}: UseCesiumViewCameraArgs) {
  const followEnabled = props.followEnabled ?? true;
  const planningAltitudeM = props.planningAltitudeM ?? 25;

  const applyCamera = () => {
    const CesiumModule = refs.cesiumRef.current;
    const viewer = refs.viewerRef.current;
    if (!CesiumModule || !viewer) return;

    applyCesiumCameraMode({
      CesiumModule,
      viewer,
      viewMode: props.viewMode,
      zoom: props.zoom,
      followEnabled,
      planningAltitudeM,
      lockCameraToPlanningAltitude: props.lockCameraToPlanningAltitude ?? false,
      latestValuesRef: refs.latestValuesRef,
      droneEntityRef: refs.droneEntityRef,
      userInteractingRef: refs.userInteractingRef,
      lastCameraSignatureRef: refs.lastCameraSignatureRef,
      rafRef: refs.rafRef,
    });
  };

  useEffect(() => {
    applyCamera();
    return () => {
      if (refs.rafRef.current != null) cancelAnimationFrame(refs.rafRef.current);
      refs.rafRef.current = null;
    };
  }, [
    props.viewMode,
    cameraCenterKey,
    props.zoom,
    hasDroneCenter,
    fieldCameraView?.center.lat,
    fieldCameraView?.center.lng,
    fieldCameraView?.topHeight,
    planningAltitudeM,
    props.lockCameraToPlanningAltitude,
    props.focusRequestToken,
    followEnabled,
    refs,
  ]);

  useEffect(() => {
    if (props.selectedWaypointIndex == null) return;
    const waypoint = props.waypoints[props.selectedWaypointIndex];
    if (!waypoint) return;
    const viewer = refs.viewerRef.current;
    const CesiumModule = refs.cesiumRef.current;
    if (!viewer || !CesiumModule) return;
    viewer.trackedEntity = undefined;
    viewer.camera.flyTo({
      destination: CesiumModule.Cartesian3.fromDegrees(waypoint.lon, waypoint.lat, 400),
      duration: 0.5,
    });
  }, [props.selectedWaypointIndex, props.waypoints, refs]);

  useEffect(() => {
    if (props.focusRequestToken == null) return;
    const ring = props.focusRing ?? props.fieldBoundary;
    if (!ring || ring.length < 3) return;
    const viewer = refs.viewerRef.current;
    const CesiumModule = refs.cesiumRef.current;
    if (!viewer || !CesiumModule) return;

    const nextFieldView = computeFieldCameraView(ring);
    if (!nextFieldView) return;

    refs.lastCameraSignatureRef.current = null;
    viewer.trackedEntity = undefined;
    const pitch =
      props.viewMode === "top"
        ? CesiumModule.Math.toRadians(-90)
        : CesiumModule.Math.toRadians(-45);
    viewer.camera.flyTo({
      destination: CesiumModule.Cartesian3.fromDegrees(
        nextFieldView.center.lng,
        nextFieldView.center.lat,
        nextFieldView.topHeight,
      ),
      orientation: {
        heading: 0,
        pitch,
        roll: 0,
      },
      duration: 0.6,
    });
  }, [
    props.fieldBoundary,
    props.focusRequestToken,
    props.focusRing,
    props.viewMode,
    refs,
  ]);
}
