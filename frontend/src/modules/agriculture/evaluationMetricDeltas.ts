import type { MetricSummary } from "./visionTypes";

export type MetricComparisonFormat = "ratio" | "fps" | "latency_ms" | "size_mb";

export type MetricDeltaDirection = "better" | "worse" | "equal" | "missing";

export type MetricComparisonSpec = {
  key: keyof MetricSummary;
  label: string;
  description: string;
  format: MetricComparisonFormat;
  higherIsBetter: boolean;
};

export const CORE_COMPARISON_METRICS: MetricComparisonSpec[] = [
  {
    key: "map50",
    label: "mAP50",
    description: "Mean average precision at 50% box overlap.",
    format: "ratio",
    higherIsBetter: true,
  },
  {
    key: "map50_95",
    label: "mAP50–95",
    description: "Mean AP across stricter overlap thresholds.",
    format: "ratio",
    higherIsBetter: true,
  },
  {
    key: "precision",
    label: "Precision",
    description: "Share of detections that were correct.",
    format: "ratio",
    higherIsBetter: true,
  },
  {
    key: "recall",
    label: "Recall",
    description: "Share of labeled objects the model found.",
    format: "ratio",
    higherIsBetter: true,
  },
];

export const OPTIONAL_COMPARISON_METRICS: MetricComparisonSpec[] = [
  {
    key: "inference_fps",
    label: "Inference FPS",
    description: "Measured inference throughput when available.",
    format: "fps",
    higherIsBetter: true,
  },
  {
    key: "inference_latency_ms",
    label: "Inference latency",
    description: "Measured inference latency when available.",
    format: "latency_ms",
    higherIsBetter: false,
  },
  {
    key: "model_size_mb",
    label: "Model size",
    description: "Published weights size when available.",
    format: "size_mb",
    higherIsBetter: false,
  },
];

export type MetricDelta = {
  direction: MetricDeltaDirection;
  label: string;
  tone: "success.main" | "error.main" | "text.secondary";
};

function finiteNumber(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function compareMetricValues(
  current: number | null | undefined,
  baseline: number | null | undefined,
  options: { higherIsBetter: boolean; epsilon?: number },
): MetricDeltaDirection {
  const { higherIsBetter, epsilon = 1e-6 } = options;
  const left = finiteNumber(current);
  const right = finiteNumber(baseline);
  if (left == null || right == null) {
    return "missing";
  }
  const delta = left - right;
  if (Math.abs(delta) <= epsilon) {
    return "equal";
  }
  const improved = higherIsBetter ? delta > 0 : delta < 0;
  return improved ? "better" : "worse";
}

export function formatMetricDelta(
  spec: MetricComparisonSpec,
  current: number | null | undefined,
  baseline: number | null | undefined,
): MetricDelta {
  const direction = compareMetricValues(current, baseline, {
    higherIsBetter: spec.higherIsBetter,
  });
  if (direction === "missing") {
    return { direction, label: "—", tone: "text.secondary" };
  }
  const left = finiteNumber(current)!;
  const right = finiteNumber(baseline)!;
  const rawDelta = left - right;
  if (direction === "equal") {
    return { direction, label: "No change", tone: "text.secondary" };
  }
  const tone = direction === "better" ? "success.main" : "error.main";
  if (spec.format === "ratio") {
    const signed = `${rawDelta >= 0 ? "+" : ""}${(rawDelta * 100).toFixed(1)} pp`;
    return { direction, label: signed, tone };
  }
  if (spec.format === "fps") {
    const signed = `${rawDelta >= 0 ? "+" : ""}${rawDelta.toFixed(1)} FPS`;
    return { direction, label: signed, tone };
  }
  if (spec.format === "latency_ms") {
    const signed = `${rawDelta >= 0 ? "+" : ""}${rawDelta.toFixed(0)} ms`;
    return { direction, label: signed, tone };
  }
  const signed = `${rawDelta >= 0 ? "+" : ""}${rawDelta.toFixed(1)} MB`;
  return { direction, label: signed, tone };
}

export function visibleComparisonMetrics(
  current: MetricSummary,
  baseline: MetricSummary,
): MetricComparisonSpec[] {
  const optional = OPTIONAL_COMPARISON_METRICS.filter((metric) => {
    const currentValue = current[metric.key];
    const baselineValue = baseline[metric.key];
    return currentValue != null || baselineValue != null;
  });
  return [...CORE_COMPARISON_METRICS, ...optional];
}
