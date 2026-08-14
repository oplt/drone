import { useEffect, useRef } from "react";
import type * as Cesium from "cesium";
import type { CesiumBootstrapContextRefs } from "../adapters/cesium/cesiumViewerBootstrap";
import type { CesiumMapProps, DrawMode, LatLng } from "../adapters/cesium/cesiumMapTypes";

export type CesiumLatestValues = {
  droneCenter: LatLng | null;
  center: LatLng;
  safeHeadingRad: number;
  fieldCameraView: { center: LatLng; topHeight: number } | null;
};

export function useCesiumMapRefs(props: CesiumMapProps) {
  const drawModeRef = useRef<DrawMode>("none");
  const onDrawCompleteRef = useRef(props.onDrawComplete);
  const onBoundaryDrawStartedRef = useRef(props.onBoundaryDrawStarted);
  const onBoundaryDrawProgressRef = useRef(props.onBoundaryDrawProgress);
  const drawHandlerRef = useRef<Cesium.ScreenSpaceEventHandler | null>(null);
  const drawAnchorsRef = useRef<Cesium.Entity[]>([]);
  const drawTempEntityRef = useRef<Cesium.Entity | null>(null);
  const drawFloatingPointRef = useRef<Cesium.Entity | null>(null);
  const drawPositionsRef = useRef<Cesium.Cartesian3[]>([]);
  const drawFreehandActiveRef = useRef(false);
  const drawIsActiveRef = useRef(false);
  const drawFloatingCartesianRef = useRef<Cesium.Cartesian3 | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const cesiumRef = useRef<typeof Cesium | null>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const clickHandlerRef = useRef<Cesium.ScreenSpaceEventHandler | null>(null);
  const rafRef = useRef<number | null>(null);
  const droneEntityRef = useRef<Cesium.Entity | null>(null);
  const polylineEntityRef = useRef<Cesium.Entity | null>(null);
  const waypointPolygonEntityRef = useRef<Cesium.Entity | null>(null);
  const plannedRouteEntityRef = useRef<Cesium.Entity | null>(null);
  const fieldBoundaryEntityRef = useRef<Cesium.Entity | null>(null);
  const exclusionZoneEntityRefs = useRef<Cesium.Entity[]>([]);
  const waypointEntityRefs = useRef<Cesium.Entity[]>([]);
  const fieldTilesetRef = useRef<Cesium.Cesium3DTileset | null>(null);
  const fieldTilesetUrlRef = useRef<string | null>(props.fieldTilesetUrl ?? null);
  const tilesetLoadSeqRef = useRef(0);
  const onPickLatLngRef = useRef(props.onPickLatLng);
  const onFieldBoundaryClickRef = useRef(props.onFieldBoundaryClick);
  const onSelectWaypointRef = useRef(props.onSelectWaypoint);
  const lastCameraSignatureRef = useRef<string | null>(null);
  const latestValuesRef = useRef<CesiumLatestValues>({
    droneCenter: props.droneCenter,
    center: props.center,
    safeHeadingRad: 0,
    fieldCameraView: null,
  });
  const userInteractingRef = useRef(false);
  const interactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewerReadyRef = useRef(false);

  useEffect(() => {
    drawModeRef.current = props.drawMode ?? "none";
  }, [props.drawMode]);
  useEffect(() => {
    onDrawCompleteRef.current = props.onDrawComplete;
  }, [props.onDrawComplete]);
  useEffect(() => {
    onBoundaryDrawStartedRef.current = props.onBoundaryDrawStarted;
  }, [props.onBoundaryDrawStarted]);
  useEffect(() => {
    onBoundaryDrawProgressRef.current = props.onBoundaryDrawProgress;
  }, [props.onBoundaryDrawProgress]);
  useEffect(() => {
    onPickLatLngRef.current = props.onPickLatLng;
  }, [props.onPickLatLng]);
  useEffect(() => {
    onFieldBoundaryClickRef.current = props.onFieldBoundaryClick;
  }, [props.onFieldBoundaryClick]);
  useEffect(() => {
    onSelectWaypointRef.current = props.onSelectWaypoint;
  }, [props.onSelectWaypoint]);
  useEffect(() => {
    fieldTilesetUrlRef.current = props.fieldTilesetUrl ?? null;
  }, [props.fieldTilesetUrl]);

  const bootstrapRefs: CesiumBootstrapContextRefs = {
    cesiumRef,
    viewerRef,
    clickHandlerRef,
    viewerReadyRef,
    drawModeRef,
    onSelectWaypointRef,
    onPickLatLngRef,
    onFieldBoundaryClickRef,
    latestValuesRef,
    entityRefs: {
      polylineEntityRef,
      waypointPolygonEntityRef,
      plannedRouteEntityRef,
      fieldBoundaryEntityRef,
      exclusionZoneEntityRefs,
      waypointEntityRefs,
      droneEntityRef,
    },
    fieldTilesetRef,
    tilesetLoadSeqRef,
    userInteractingRef,
    lastCameraSignatureRef,
    rafRef,
  };

  return {
    hostRef,
    drawHandlerRef,
    drawAnchorsRef,
    drawTempEntityRef,
    drawFloatingPointRef,
    drawPositionsRef,
    drawFreehandActiveRef,
    drawIsActiveRef,
    drawFloatingCartesianRef,
    drawModeRef,
    onDrawCompleteRef,
    onBoundaryDrawStartedRef,
    onBoundaryDrawProgressRef,
    cesiumRef,
    viewerRef,
    rafRef,
    droneEntityRef,
    latestValuesRef,
    userInteractingRef,
    interactionTimerRef,
    lastCameraSignatureRef,
    bootstrapRefs,
  };
}

export type CesiumMapRefs = ReturnType<typeof useCesiumMapRefs>;
