import type { LonLat } from "../../fields";
import {
  type MissionMapEngine,
  type RouteDrawMode,
  type RouteDrawToolMode,
  type TerraDrawEditorMode,
  type TerraDrawFeature,
} from "../../maps";
import type { AnimalFarmWaypoint } from "../animalFarmPageTypes";

export function waypointsFromTerraSnapshot(
  snapshot: TerraDrawFeature[],
  alt: number,
): AnimalFarmWaypoint[] {
  const next: AnimalFarmWaypoint[] = [];
  snapshot.forEach((feature) => {
    const geometry = feature.geometry;
    if (geometry?.type === "Point" && Array.isArray(geometry.coordinates)) {
      const [lon, lat] = geometry.coordinates as [number, number];
      if (Number.isFinite(lat) && Number.isFinite(lon)) next.push({ lat, lon, alt });
    }
    if (geometry?.type === "LineString" && Array.isArray(geometry.coordinates)) {
      (geometry.coordinates as [number, number][]).forEach(([lon, lat]) => {
        if (Number.isFinite(lat) && Number.isFinite(lon)) next.push({ lat, lon, alt });
      });
    }
  });
  return next;
}

export function farmBorderFromTerraSnapshot(snapshot: TerraDrawFeature[]): LonLat[] | null {
  const boundary = [...snapshot]
    .reverse()
    .find((feature) => {
      if (!feature.id || !feature.geometry) return false;
      if (feature.geometry.type === "Polygon") return true;
      if (feature.geometry.type === "LineString") {
        const coords = feature.geometry.coordinates as [number, number][] | undefined;
        return Array.isArray(coords) && coords.length >= 3;
      }
      return false;
    });
  if (!boundary?.geometry) return null;
  if (boundary.geometry.type === "Polygon") {
    const coords = (boundary.geometry.coordinates as [number, number][][])[0];
    return coords.map(([lon, lat]) => [lon, lat] as LonLat);
  }
  const coords = boundary.geometry.coordinates as [number, number][];
  return coords.map(([lon, lat]) => [lon, lat] as LonLat);
}

export function terraDrawFeatureCount(snapshot: TerraDrawFeature[]): number {
  return snapshot.filter((feature) => feature.id != null).length;
}

export function googleTerraDrawModeForTool(toolMode: RouteDrawToolMode): TerraDrawEditorMode {
  const googleModeMap: Record<RouteDrawToolMode, TerraDrawEditorMode> = {
    none: "select",
    point: "point",
    polyline: "linestring",
    polygon: "polygon",
    rectangle: "rectangle",
    circle: "circle",
    triangle: "polygon",
  };
  return googleModeMap[toolMode];
}

export function flatDrawModeForTool(toolMode: RouteDrawToolMode): RouteDrawMode {
  const flatModeMap: Record<RouteDrawToolMode, RouteDrawMode> = {
    none: "none",
    point: "point",
    polyline: "polyline",
    polygon: "polygon",
    rectangle: "rectangle",
    circle: "circle",
    triangle: "triangle",
  };
  return flatModeMap[toolMode];
}

export function shouldIgnoreGoogleMapClick(
  mapEngine: MissionMapEngine,
  terraDrawMode: TerraDrawEditorMode,
  drawMode: RouteDrawMode,
): boolean {
  if (mapEngine === "google" && terraDrawMode !== "static" && terraDrawMode !== "select") {
    return true;
  }
  return drawMode === "none";
}
