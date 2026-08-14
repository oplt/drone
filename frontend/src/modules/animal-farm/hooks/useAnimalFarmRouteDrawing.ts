import { useCallback, useMemo, useState } from "react";
import { stripClosedRing, type LonLat } from "../../fields";
import {
  type MissionMapEngine,
  type RouteDrawMode,
  type RouteDrawToolMode,
  type TerraDrawEditorMode,
  type TerraDrawFeature,
} from "../../maps";
import type { AnimalFarmWaypoint } from "../animalFarmPageTypes";
import {
  flatDrawModeForTool,
  googleTerraDrawModeForTool,
  shouldIgnoreGoogleMapClick,
  terraDrawFeatureCount,
  waypointsFromTerraSnapshot,
} from "../utils/animalFarmRouteDrawingUtils";
import { useAnimalFarmFarmBorderDrawing } from "./useAnimalFarmFarmBorderDrawing";

type UseAnimalFarmRouteDrawingOptions = {
  addError: (message: string) => void;
  alt: number;
  mapEngine: MissionMapEngine;
};

export function useAnimalFarmRouteDrawing({
  addError,
  alt,
  mapEngine,
}: UseAnimalFarmRouteDrawingOptions) {
  const border = useAnimalFarmFarmBorderDrawing({ addError });
  const [waypoints, setWaypoints] = useState<AnimalFarmWaypoint[]>([]);
  const [drawMode, setDrawMode] = useState<RouteDrawMode>("point");
  const [terraDrawMode, setTerraDrawMode] = useState<TerraDrawEditorMode>("point");
  const [, setTerraDrawReady] = useState(false);
  const [terraDrawFeatureCountState, setTerraDrawFeatureCount] = useState(0);
  const [drawWaypointHistory, setDrawWaypointHistory] = useState<number[]>([]);

  const syncRouteFromTerraDraw = useCallback(
    (snapshot: TerraDrawFeature[]) => {
      setTerraDrawFeatureCount(terraDrawFeatureCount(snapshot));
      setWaypoints(waypointsFromTerraSnapshot(snapshot, alt));
    },
    [alt],
  );

  const handleTerraSnapshotChange = useCallback(
    (snapshot: TerraDrawFeature[]) => {
      syncRouteFromTerraDraw(snapshot);
      border.syncFarmBorderFromSnapshot(snapshot);
      border.shapePrompt.handleSnapshotChange(snapshot);
    },
    [border, syncRouteFromTerraDraw],
  );

  const handleRouteDrawComplete = useCallback(
    (result: {
      type: "point" | "polyline" | "polygon";
      coordinates: [number, number] | [number, number][];
    }) => {
      if (result.type === "polygon") {
        const ring = stripClosedRing(
          (result.coordinates as [number, number][]).map(([lon, lat]) => [lon, lat] as LonLat),
        );
        if (ring.length >= 3) border.setFarmBorder(ring);
        setDrawMode("none");
        return;
      }
      if (result.type === "polyline") {
        const coordinates = result.coordinates as [number, number][];
        setWaypoints(coordinates.map(([lon, lat]) => ({ lat, lon, alt })));
        setDrawWaypointHistory([coordinates.length]);
        setDrawMode("point");
        return;
      }
      if (result.type === "point") {
        const [lon, lat] = result.coordinates as [number, number];
        setWaypoints((prev) => [...prev, { lat, lon, alt }]);
        setDrawWaypointHistory((prev) => [...prev, 1]);
      }
    },
    [alt, border],
  );

  const handleRouteToolModeChange = useCallback(
    (toolMode: RouteDrawToolMode) => {
      border.shapePrompt.resetBoundaryDrawSession();
      if (mapEngine === "google") {
        setTerraDrawMode(googleTerraDrawModeForTool(toolMode));
        return;
      }
      setDrawMode(flatDrawModeForTool(toolMode));
    },
    [border.shapePrompt, mapEngine],
  );

  const onMapClick = useCallback(
    (e: google.maps.MapMouseEvent) => {
      if (shouldIgnoreGoogleMapClick(mapEngine, terraDrawMode, drawMode)) return;
      if (!e.latLng) return;
      const lat = e.latLng.lat();
      const lng = e.latLng.lng();
      setWaypoints((prev) => [...prev, { lat, lon: lng, alt }]);
    },
    [alt, drawMode, mapEngine, terraDrawMode],
  );

  const undo = useCallback(() => {
    if (mapEngine === "google" && border.terraDrawRef.current) {
      border.shapePrompt.deleteSelectedDrawing(syncRouteFromTerraDraw);
      return;
    }
    setWaypoints((prev) => {
      const removeCount = drawWaypointHistory.at(-1) ?? 1;
      return prev.slice(0, Math.max(0, prev.length - removeCount));
    });
    setDrawWaypointHistory((prev) => prev.slice(0, -1));
  }, [border.shapePrompt, border.terraDrawRef, drawWaypointHistory, mapEngine, syncRouteFromTerraDraw]);

  const clearWaypoints = useCallback(() => {
    setWaypoints([]);
    setDrawWaypointHistory([]);
  }, []);

  const applyPlannedRoute = useCallback((plan: { waypoints: AnimalFarmWaypoint[] }) => {
    setWaypoints(plan.waypoints);
  }, []);

  const polylinePath = useMemo(
    () => waypoints.map((point) => ({ lat: point.lat, lng: point.lon })),
    [waypoints],
  );

  return {
    terraDrawRef: border.terraDrawRef,
    waypoints,
    setWaypoints,
    farmBorder: border.farmBorder,
    farmBorderName: border.farmBorderName,
    setFarmBorderName: border.setFarmBorderName,
    drawMode,
    setDrawMode,
    terraDrawMode,
    setTerraDrawReady,
    terraDrawFeatureCount: terraDrawFeatureCountState,
    shapePrompt: border.shapePrompt,
    farmBorderDraw: border.farmBorderDraw,
    savingFarmBorder: border.savingFarmBorder,
    handleTerraSnapshotChange,
    handleRouteDrawComplete,
    handleRouteToolModeChange,
    handleFarmBorderSave: border.handleFarmBorderSave,
    onMapClick,
    undo,
    clearWaypoints,
    applyPlannedRoute,
    polylinePath,
  };
}
