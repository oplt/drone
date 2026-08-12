import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { visionKeys } from "../hooks/useVisionModels";
import type { VisionDataset, VisionTrainingRun } from "../visionTypes";
import { VisionTrainingWorkspace } from "./VisionTrainingWorkspace";

const dataset: VisionDataset = {
  id: "dataset-1",
  project_id: "project-1",
  version: 1,
  status: "locked",
  source_count: 1,
  image_count: 3,
  selected_count: 3,
  labeled_count: 3,
  reviewed_count: 3,
  train_count: 1,
  val_count: 1,
  test_count: 1,
  manifest_checksum: "checksum",
  locked_at: "2026-08-01T00:00:00Z",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

describe("vision training workspace", () => {
  it("surfaces persisted training and evaluation failures", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity } },
    });
    const failedRun: VisionTrainingRun = {
      id: "run-1",
      project_id: "project-1",
      dataset_id: dataset.id,
      status: "failed",
      trainer: "ultralytics",
      base_model: "yolo26s.pt",
      preset: "balanced",
      epochs: 50,
      total_epochs: 50,
      image_size: 640,
      batch_size: 8,
      device: "cpu",
      progress: 42,
      current_epoch: 21,
      metrics: {},
      error: "Model evaluation failed.",
      model_version_id: null,
      started_at: "2026-08-01T00:00:00Z",
      finished_at: "2026-08-01T00:20:00Z",
      created_at: "2026-08-01T00:00:00Z",
    };
    client.setQueryData(visionKeys.trainingRuns("project-1"), [failedRun]);

    render(
      <QueryClientProvider client={client}>
        <VisionTrainingWorkspace projectId="project-1" dataset={dataset} />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Model evaluation failed.")).toBeVisible();
    expect(screen.getByText("failed")).toBeVisible();
  });
});
