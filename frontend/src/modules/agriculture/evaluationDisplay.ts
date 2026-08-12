import type { MetricSummary, VisionModelVersion } from "./visionTypes";

export const EVALUATION_METRICS: Array<{
  key: keyof MetricSummary;
  label: string;
  description: string;
}> = [
  { key: "map50", label: "mAP50", description: "Mean average precision at 50% box overlap." },
  { key: "precision", label: "Precision", description: "Share of detections that were correct." },
  { key: "recall", label: "Recall", description: "Share of labeled objects the model found." },
  { key: "map50_95", label: "mAP50–95", description: "Mean AP across stricter overlap thresholds." },
];

export function percent(value: number | null | undefined): string {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

export function metricSummary(version: VisionModelVersion): MetricSummary {
  const nested = version.metrics.summary;
  return nested && typeof nested === "object" ? (nested as MetricSummary) : {};
}
