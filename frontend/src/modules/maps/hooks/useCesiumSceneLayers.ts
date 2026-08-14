import { useEffect } from "react";
import { loadCesiumFieldTileset } from "../adapters/cesium/cesiumFieldTileset";
import { updateCesiumDroneEntity } from "../adapters/cesium/cesiumDroneEntity";
import { syncCesiumSceneEntities } from "../adapters/cesium/cesiumSceneEntities";
import type { CesiumMapProps } from "../adapters/cesium/cesiumMapTypes";
import type { CesiumMapRefs } from "./useCesiumMapRefs";

type UseCesiumSceneLayersArgs = {
  refs: CesiumMapRefs;
  safeHeadingRad: number;
  props: Pick<
    CesiumMapProps,
    | "drawMode"
    | "waypoints"
    | "fieldBoundary"
    | "plannedRoute"
    | "exclusionZones"
    | "drawnBoundarySelected"
    | "selectedWaypointIndex"
    | "planningAltitudeM"
    | "fieldTilesetUrl"
    | "droneCenter"
  >;
};

export function useCesiumSceneLayers({
  refs,
  props,
  safeHeadingRad,
}: UseCesiumSceneLayersArgs) {
  const drawMode = props.drawMode ?? "none";
  const exclusionZones = props.exclusionZones ?? [];
  const planningAltitudeM = props.planningAltitudeM ?? 25;

  useEffect(() => {
    const CesiumModule = refs.cesiumRef.current;
    const viewer = refs.viewerRef.current;
    if (!CesiumModule || !viewer) return;

    syncCesiumSceneEntities({
      CesiumModule,
      viewer,
      drawMode,
      waypoints: props.waypoints,
      fieldBoundary: props.fieldBoundary ?? null,
      plannedRoute: props.plannedRoute ?? null,
      exclusionZones,
      drawnBoundarySelected: props.drawnBoundarySelected ?? false,
      selectedWaypointIndex: props.selectedWaypointIndex ?? null,
      planningAltitudeM,
      latestValuesRef: refs.latestValuesRef,
      entityRefs: refs.bootstrapRefs.entityRefs,
    });
  }, [
    drawMode,
    props.waypoints,
    props.fieldBoundary,
    props.plannedRoute,
    exclusionZones,
    props.drawnBoundarySelected,
    props.selectedWaypointIndex,
    planningAltitudeM,
    refs,
  ]);

  useEffect(() => {
    const CesiumModule = refs.cesiumRef.current;
    const viewer = refs.viewerRef.current;
    if (!CesiumModule || !viewer) return;

    updateCesiumDroneEntity({
      CesiumModule,
      viewer,
      droneEntityRef: refs.droneEntityRef,
      latestValues: refs.latestValuesRef.current,
      planningAltitudeM,
    });
  }, [props.droneCenter, safeHeadingRad, planningAltitudeM, refs]);

  useEffect(() => {
    const CesiumModule = refs.cesiumRef.current;
    const viewer = refs.viewerRef.current;
    if (!CesiumModule || !viewer) return;

    void loadCesiumFieldTileset({
      CesiumModule,
      viewer,
      url: props.fieldTilesetUrl ?? null,
      fieldTilesetRef: refs.bootstrapRefs.fieldTilesetRef,
      tilesetLoadSeqRef: refs.bootstrapRefs.tilesetLoadSeqRef,
      viewerRef: refs.viewerRef,
    });
  }, [props.fieldTilesetUrl, refs]);
}
