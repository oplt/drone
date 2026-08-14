import { describe, expect, it } from "vitest";
import {
  compareMetricValues,
  formatMetricDelta,
  visibleComparisonMetrics,
} from "./evaluationMetricDeltas";

describe("evaluationMetricDeltas", () => {
  it("marks higher metric values as better for ratio metrics", () => {
    expect(
      compareMetricValues(0.91, 0.88, { higherIsBetter: true }),
    ).toBe("better");
    expect(
      compareMetricValues(0.85, 0.88, { higherIsBetter: true }),
    ).toBe("worse");
  });

  it("formats ratio deltas in percentage points", () => {
    const delta = formatMetricDelta(
      {
        key: "map50",
        label: "mAP50",
        description: "",
        format: "ratio",
        higherIsBetter: true,
      },
      0.913,
      0.884,
    );
    expect(delta.label).toBe("+2.9 pp");
    expect(delta.direction).toBe("better");
    expect(delta.tone).toBe("success.main");
  });

  it("treats equal values as unchanged", () => {
    const delta = formatMetricDelta(
      {
        key: "recall",
        label: "Recall",
        description: "",
        format: "ratio",
        higherIsBetter: true,
      },
      0.87,
      0.87,
    );
    expect(delta.direction).toBe("equal");
    expect(delta.label).toBe("No change");
  });

  it("degrades gracefully when either metric is missing", () => {
    const delta = formatMetricDelta(
      {
        key: "precision",
        label: "Precision",
        description: "",
        format: "ratio",
        higherIsBetter: true,
      },
      0.9,
      null,
    );
    expect(delta.direction).toBe("missing");
    expect(delta.label).toBe("—");
  });

  it("includes optional metrics only when data exists", () => {
    const metrics = visibleComparisonMetrics(
      { map50: 0.9, inference_fps: 24 },
      { map50: 0.88 },
    );
    expect(metrics.map((metric) => metric.key)).toEqual([
      "map50",
      "map50_95",
      "precision",
      "recall",
      "inference_fps",
    ]);
  });
});
