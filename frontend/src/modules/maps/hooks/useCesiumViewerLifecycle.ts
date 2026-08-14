import { useEffect } from "react";
import { bootstrapCesiumViewer } from "../adapters/cesium/cesiumViewerBootstrap";
import type { CesiumMapProps } from "../adapters/cesium/cesiumMapTypes";
import type { CesiumMapRefs } from "./useCesiumMapRefs";

type UseCesiumViewerLifecycleArgs = {
  refs: CesiumMapRefs;
  props: Pick<
    CesiumMapProps,
    | "useWorldTerrain"
    | "drawMode"
    | "waypoints"
    | "fieldBoundary"
    | "plannedRoute"
    | "exclusionZones"
    | "drawnBoundarySelected"
    | "selectedWaypointIndex"
    | "planningAltitudeM"
    | "fieldTilesetUrl"
    | "viewMode"
    | "zoom"
    | "followEnabled"
    | "lockCameraToPlanningAltitude"
    | "droneCenter"
    | "center"
  >;
  fieldCameraView: { center: { lat: number; lng: number }; topHeight: number } | null;
};

export function useCesiumViewerLifecycle({
  refs,
  props,
  fieldCameraView,
}: UseCesiumViewerLifecycleArgs) {
  const useWorldTerrain = props.useWorldTerrain ?? true;
  const drawMode = props.drawMode ?? "none";
  const exclusionZones = props.exclusionZones ?? [];
  const planningAltitudeM = props.planningAltitudeM ?? 25;
  const followEnabled = props.followEnabled ?? true;

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const hostElement = refs.hostRef.current;
      if (!hostElement) return;

      const result = await bootstrapCesiumViewer({
        hostElement,
        isCancelled: () => cancelled,
        useWorldTerrain,
        refs: refs.bootstrapRefs,
        drawMode,
        waypoints: props.waypoints,
        fieldBoundary: props.fieldBoundary ?? null,
        plannedRoute: props.plannedRoute ?? null,
        exclusionZones,
        drawnBoundarySelected: props.drawnBoundarySelected ?? false,
        selectedWaypointIndex: props.selectedWaypointIndex ?? null,
        planningAltitudeM,
        fieldTilesetUrl: props.fieldTilesetUrl ?? null,
        viewMode: props.viewMode,
        zoom: props.zoom,
        followEnabled,
        lockCameraToPlanningAltitude: props.lockCameraToPlanningAltitude ?? false,
        fieldCameraView,
        droneCenter: props.droneCenter,
        center: props.center,
      });

      if (result.cancelled) return;
    })();

    return () => {
      cancelled = true;
      refs.bootstrapRefs.viewerReadyRef.current = false;

      if (refs.rafRef.current != null) cancelAnimationFrame(refs.rafRef.current);
      refs.rafRef.current = null;

      try {
        refs.bootstrapRefs.clickHandlerRef.current?.destroy?.();
      } catch {
        // ignore cleanup errors
      }
      refs.bootstrapRefs.clickHandlerRef.current = null;

      refs.bootstrapRefs.tilesetLoadSeqRef.current += 1;
      const viewer = refs.viewerRef.current;
      if (viewer && refs.bootstrapRefs.fieldTilesetRef.current) {
        try {
          viewer.scene.primitives.remove(refs.bootstrapRefs.fieldTilesetRef.current);
        } catch {
          // ignore cleanup errors
        }
      }
      refs.bootstrapRefs.fieldTilesetRef.current = null;

      try {
        viewer?.destroy?.();
      } catch {
        // ignore cleanup errors
      }
      refs.viewerRef.current = null;
      refs.cesiumRef.current = null;
    };
  }, [useWorldTerrain]);
}
