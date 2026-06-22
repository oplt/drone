import type { TerraDraw } from "terra-draw";
import type { TerraDrawFeature } from "../../maps/components/TerraDrawController";
import {
  findTerraDrawFeature,
  isMainDrawnShapeFeature,
  resolveMainDrawnShapeFeatureId,
} from "./mapShapePromptUtils";

export function resolveTerraDrawDeleteTarget(
  snapshot: TerraDrawFeature[],
  selectedFeatureId: string | number | null,
  isRemovable?: (feature: TerraDrawFeature) => boolean,
): TerraDrawFeature | undefined {
  const resolvedId = resolveMainDrawnShapeFeatureId(snapshot, selectedFeatureId);
  if (resolvedId != null) {
    return findTerraDrawFeature(snapshot, resolvedId);
  }

  const predicate = isRemovable ?? isMainDrawnShapeFeature;
  return [...snapshot].reverse().find((feature) => predicate(feature));
}

export function deleteMainDrawnShape(
  terraDraw: TerraDraw,
  selectedFeatureId: string | number | null,
): TerraDrawFeature[] {
  const snapshot = terraDraw.getSnapshot() as TerraDrawFeature[];
  const targetId = resolveMainDrawnShapeFeatureId(snapshot, selectedFeatureId);

  if (targetId == null) {
    return snapshot;
  }

  if (terraDraw.hasFeature(targetId)) {
    terraDraw.removeFeatures([targetId]);
    return terraDraw.getSnapshot() as TerraDrawFeature[];
  }

  const fallbackIds = snapshot
    .filter(isMainDrawnShapeFeature)
    .map((feature) => feature.id)
    .filter((id): id is string | number => id != null);

  if (fallbackIds.length > 0) {
    terraDraw.removeFeatures(fallbackIds);
  }

  return terraDraw.getSnapshot() as TerraDrawFeature[];
}

/** @deprecated Prefer deleteMainDrawnShape */
export function deleteSelectedOrLatestTerraDrawFeature(
  terraDraw: TerraDraw,
  selectedFeatureId: string | number | null,
  isRemovable: (feature: TerraDrawFeature) => boolean,
): TerraDrawFeature[] {
  const snapshot = terraDraw.getSnapshot() as TerraDrawFeature[];
  const target = resolveTerraDrawDeleteTarget(snapshot, selectedFeatureId, isRemovable);
  if (target?.id == null) {
    return snapshot;
  }

  terraDraw.removeFeatures([target.id]);
  return terraDraw.getSnapshot() as TerraDrawFeature[];
}
