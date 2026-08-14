import { describe, expect, it } from "vitest";
import type { VisionTrainingRun } from "./visionTypes";
import {
  buildVisionTrainingRunListPresentation,
  extractVisionTrainingRunMetrics,
  formatVisionTrainingStatusLabel,
} from "./trainingRunPresentation";

const baseRun: VisionTrainingRun = {
  id: "run-1",
  project_id: "project-1",
  dataset_id: "dataset-1",
  status: "running",
  trainer: "ultralytics",
  base_model: "yolo26s.pt",
  preset: "high_accuracy",
  epochs: 50,
  total_epochs: 50,
  image_size: 640,
  batch_size: 8,
  device: "cuda:0",
  progress: 42,
  current_epoch: 21,
  metrics: {
    training: {
      "train/box_loss": 1.2345,
      "val/box_loss": 0.9876,
      "metrics/precision(B)": 0.71,
      "metrics/recall(B)": 0.66,
    },
  },
  error: null,
  model_version_id: null,
  started_at: "2026-08-01T00:00:00Z",
  finished_at: null,
  created_at: "2026-08-01T00:00:00Z",
};

describe("vision training run presentation", () => {
  it("builds compact list cards with consistent status labels", () => {
    const list = buildVisionTrainingRunListPresentation(baseRun);
    expect(list.modelLabel).toBe("yolo26s.pt");
    expect(list.presetLabel).toBe("High Accuracy");
    expect(list.statusLabel).toBe("Running");
    expect(list.epochLabel).toBe("21/50");
    expect(list.progressPercent).toBe(42);
    expect(list.device).toBe("cuda:0");
    expect(list.isCancellable).toBe(true);
  });

  it("extracts advanced metrics for the detail view", () => {
    const metrics = extractVisionTrainingRunMetrics({
      ...baseRun,
      status: "completed",
      current_epoch: 50,
      finished_at: "2026-08-01T00:50:00Z",
      model_version_id: "version-1",
      metrics: {
        summary: {
          precision: 0.82,
          recall: 0.79,
          map50: 0.76,
          map50_95: 0.58,
        },
      },
    });

    expect(formatVisionTrainingStatusLabel("cancelling")).toBe("Cancelling");
    expect(metrics.precision).toBe(0.82);
    expect(metrics.map50_95).toBe(0.58);
    expect(metrics.epochDurationSeconds).toBeCloseTo(60, 0);
    expect(metrics.bestEpoch).toBe(50);
    expect(metrics.evaluationStatus).toBe("Evaluation completed");
    expect(metrics.checkpointStatus).toBe("Checkpoint published");
  });
});
