const REASON_COPY: Record<string, string> = {
  clearance_rejection_ratio_high: "many scan positions were too close to obstacles",
  missing_occupancy_grid: "no reliable free-space map was saved",
  too_many_targets_per_rack: "the detector found an unrealistic number of shelf targets",
  weak_esdf: "the distance map was too sparse",
  tf_instability: "mapping reset during the scan",
  insufficient_detected_structure: "not enough warehouse structure was detected",
  missing_esdf_topic: "distance-map data was missing at the end of the scan",
};

export function describeStructureQualityReasons(reasons: string[] = []): string[] {
  return reasons.map((reason) => REASON_COPY[reason] ?? reason.replaceAll("_", " "));
}

export function structureNeedsReviewMessage(reasons: string[] = []): string {
  const descriptions = describeStructureQualityReasons(reasons);
  if (descriptions.length === 0) {
    return "Auto-detect found a possible layout, but the map is not reliable enough to use yet.";
  }
  return `Auto-detect found a possible layout, but kept it inactive because ${descriptions.join(", ")}.`;
}
