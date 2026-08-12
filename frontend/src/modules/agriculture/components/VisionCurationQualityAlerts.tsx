import { Alert, Stack } from "@mui/material";
import type { VisionCurationSummary } from "../visionTypes";

export function VisionCurationQualityAlerts({
  summary,
  context,
}: {
  summary?: VisionCurationSummary | null;
  context: "dataset" | "training";
}) {
  if (!summary) {
    return null;
  }
  const leakageCount =
    summary.split_leakage?.nearest_cross_split_similarity_count ?? 0;
  const leakageRisk = Boolean(
    summary.split_leakage_risk || summary.quality_flags?.split_leakage_risk,
  );
  const clusterCount = summary.duplicate_cluster_count ?? 0;
  const rejected = summary.near_duplicate_rejected ?? 0;
  const alerts = [];
  if (leakageRisk || leakageCount > 0) {
    alerts.push(
      <Alert key="leakage" severity="warning">
        {context === "training"
          ? `Training is blocked while split leakage remains (${leakageCount} near-duplicate pair${leakageCount === 1 ? "" : "s"} across train/val/test). Clone to a new dataset version and re-curate overlapping sources.`
          : `Cross-split leakage detected (${leakageCount} near-duplicate pair${leakageCount === 1 ? "" : "s"}). Training will be blocked until source groups or near-duplicates are resolved.`}
      </Alert>,
    );
  }
  if (clusterCount > 0) {
    alerts.push(
      <Alert key="clusters" severity="info">
        {rejected > 0
          ? `${clusterCount} near-duplicate cluster${clusterCount === 1 ? "" : "s"} found; ${rejected} secondary image${rejected === 1 ? "" : "s"} excluded from selection.`
          : `${clusterCount} near-duplicate cluster${clusterCount === 1 ? "" : "s"} recorded in curation.`}
      </Alert>,
    );
  }
  if (!alerts.length) {
    return null;
  }
  return <Stack spacing={1}>{alerts}</Stack>;
}
