import type { TerraDrawFeature } from "../../maps/components/TerraDrawController";

function isGuidanceFeature(feature: TerraDrawFeature): boolean {
  const props = (feature?.properties ?? {}) as Record<string, unknown>;
  return Boolean(
    feature?.geometry?.type === "Point" &&
      (props.coordinatePoint ||
        props.closingPoint ||
        props.snappingPoint ||
        props.selectionPoint ||
        props.midPoint),
  );
}

function featureDrawMode(feature: TerraDrawFeature | undefined): string | undefined {
  const mode = feature?.properties?.mode;
  return typeof mode === "string" ? mode : undefined;
}

const BOUNDARY_DRAW_MODES = new Set([
  "polygon",
  "linestring",
  "rectangle",
  "circle",
  "freehand",
]);

const SELECTION_PROMPT_MODES = new Set(["rectangle", "circle"]);
const CREATE_PROMPT_MODES = new Set(["polygon", "linestring"]);

export function isUserDrawnBoundaryShape(
  feature: TerraDrawFeature | undefined,
): boolean {
  if (!feature?.geometry || feature.id == null) return false;
  const mode = featureDrawMode(feature);
  if (mode === "static" || isGuidanceFeature(feature)) return false;
  if (mode === "point") return false;

  if (feature.geometry.type === "Polygon") {
    return Array.isArray(
      ((feature.geometry as { coordinates?: unknown[] }).coordinates ?? [])[0],
    );
  }
  if (feature.geometry.type === "LineString") {
    const coords = feature.geometry.coordinates as [number, number][] | undefined;
    return Array.isArray(coords) && coords.length >= 3;
  }
  return false;
}

/** @deprecated Use isUserDrawnBoundaryShape */
export const isUserDrawnPolygon = isUserDrawnBoundaryShape;

export function hasUserDrawnBoundaryShape(snapshot: TerraDrawFeature[]): boolean {
  return snapshot.some((feature) => isUserDrawnBoundaryShape(feature));
}

/** @deprecated Use hasUserDrawnBoundaryShape */
export const hasUserDrawnPolygon = hasUserDrawnBoundaryShape;

export function isActiveBoundaryDrawFeature(
  feature: TerraDrawFeature | undefined,
): boolean {
  if (!feature?.geometry || feature.id == null) return false;
  const mode = featureDrawMode(feature);
  if (!mode || mode === "static" || isGuidanceFeature(feature)) return false;
  if (mode === "point") return false;

  if (mode === "linestring") {
    return feature.geometry.type === "LineString";
  }

  if (
    mode === "polygon" ||
    mode === "rectangle" ||
    mode === "circle" ||
    mode === "freehand"
  ) {
    return feature.geometry.type === "Polygon";
  }

  return false;
}

export function isBoundaryDrawMode(mode: string | undefined): boolean {
  return mode != null && BOUNDARY_DRAW_MODES.has(mode);
}

export function shouldOpenShapePromptOnSelection(
  feature: TerraDrawFeature | undefined,
): boolean {
  const mode = featureDrawMode(feature);
  return (
    mode != null &&
    SELECTION_PROMPT_MODES.has(mode) &&
    isUserDrawnBoundaryShape(feature)
  );
}

export function shouldOpenShapePromptOnCreate(
  feature: TerraDrawFeature | undefined,
): boolean {
  const mode = featureDrawMode(feature);
  return (
    mode != null &&
    CREATE_PROMPT_MODES.has(mode) &&
    isUserDrawnBoundaryShape(feature)
  );
}

export function isRemovableTerraDrawFeature(feature: TerraDrawFeature | undefined): boolean {
  if (!feature || feature.id == null) return false;
  const mode = featureDrawMode(feature);
  return mode !== "static" && !isGuidanceFeature(feature);
}

const MAIN_POLYGON_MODES = new Set(["polygon", "circle", "rectangle", "freehand"]);

export function isMainDrawnShapeFeature(feature: TerraDrawFeature | undefined): boolean {
  if (!feature?.id || isGuidanceFeature(feature)) return false;

  const mode = featureDrawMode(feature);
  if (!mode || mode === "static") return false;

  if (mode === "point") {
    return feature.geometry?.type === "Point";
  }
  if (mode === "linestring") {
    return feature.geometry?.type === "LineString";
  }
  if (MAIN_POLYGON_MODES.has(mode)) {
    return feature.geometry?.type === "Polygon";
  }

  return false;
}

function resolveParentShapeFeatureId(
  snapshot: TerraDrawFeature[],
  feature: TerraDrawFeature | undefined,
): string | number | null {
  if (!feature) return null;

  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const parentId = props.selectionPointFeatureId ?? props.coordinatePointFeatureId;
  if (parentId == null) return null;

  const parent = findTerraDrawFeature(snapshot, parentId as string | number);
  if (parent && isMainDrawnShapeFeature(parent)) {
    return parent.id ?? null;
  }

  return null;
}

export function resolveMainDrawnShapeFeatureId(
  snapshot: TerraDrawFeature[],
  selectedFeatureId: string | number | null,
): string | number | null {
  if (selectedFeatureId != null) {
    const selected = findTerraDrawFeature(snapshot, selectedFeatureId);
    if (selected && isMainDrawnShapeFeature(selected)) {
      return selected.id ?? null;
    }

    const parentId = resolveParentShapeFeatureId(snapshot, selected);
    if (parentId != null) {
      return parentId;
    }
  }

  const latest = [...snapshot].reverse().find(isMainDrawnShapeFeature);
  return latest?.id ?? null;
}

export function findTerraDrawFeature(
  snapshot: TerraDrawFeature[],
  id: string | number | null | undefined,
): TerraDrawFeature | undefined {
  if (id == null) return undefined;
  return snapshot.find((feature) => feature.id === id);
}
