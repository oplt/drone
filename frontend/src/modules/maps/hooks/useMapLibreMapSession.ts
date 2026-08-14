import type { MapLibreMapProps } from "../adapters/maplibre/maplibreMapTypes";
import { useMapLibreCamera } from "./useMapLibreCamera";
import { useMapLibreDrawing } from "./useMapLibreDrawing";
import { useMapLibreMapLifecycle } from "./useMapLibreMapLifecycle";
import { useMapLibreMapRefs } from "./useMapLibreMapRefs";
import { useMapLibreMarkers } from "./useMapLibreMarkers";
import { useMapLibreOverlays } from "./useMapLibreOverlays";
import { useMapLibreWaypointsAndRoute } from "./useMapLibreWaypointsAndRoute";

export function useMapLibreMapSession(props: MapLibreMapProps) {
  const refs = useMapLibreMapRefs(props);
  const drawMode = props.drawMode ?? "none";

  useMapLibreDrawing({
    refs,
    drawMode,
    onDrawComplete: props.onDrawComplete,
    onPickLatLng: props.onPickLatLng,
    onBoundaryDrawStarted: props.onBoundaryDrawStarted,
    onBoundaryDrawProgress: props.onBoundaryDrawProgress,
  });

  useMapLibreMapLifecycle({
    refs,
    center: props.center,
    zoom: props.zoom,
  });

  useMapLibreCamera({
    refs,
    center: props.center,
    zoom: props.zoom,
    focusRing: props.focusRing ?? null,
    focusRequestToken: props.focusRequestToken,
    followEnabled: props.followEnabled ?? true,
    droneCenter: props.droneCenter ?? null,
    selectedWaypointIndex: props.selectedWaypointIndex ?? null,
    waypoints: props.waypoints ?? [],
  });

  useMapLibreWaypointsAndRoute({
    refs,
    waypoints: props.waypoints ?? [],
    selectedWaypointIndex: props.selectedWaypointIndex ?? null,
    onSelectWaypoint: props.onSelectWaypoint,
  });

  useMapLibreMarkers({
    refs,
    droneCenter: props.droneCenter ?? null,
    userCenter: props.userCenter ?? null,
  });

  useMapLibreOverlays({
    refs,
    drawMode,
    savedFields: props.savedFields ?? [],
    selectedFieldId: props.selectedFieldId ?? null,
    fieldBoundary: props.fieldBoundary ?? null,
    drawnBoundarySelected: props.drawnBoundarySelected ?? false,
    exclusionZones: props.exclusionZones ?? [],
    plannedRoute: props.plannedRoute ?? null,
  });

  return refs.hostRef;
}
