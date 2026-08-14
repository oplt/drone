import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { visionKeys } from "../hooks/useVisionModels";
import type { VisionTrainingRun } from "../visionTypes";
import VisionTrainingRunPage from "./VisionTrainingRunPage";

const failedRun: VisionTrainingRun = {
  id: "run-1",
  project_id: "project-1",
  dataset_id: "dataset-1",
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
  metrics: {
    training: {
      "train/box_loss": 1.2,
      "val/box_loss": 0.9,
    },
  },
  error: "Model evaluation failed.",
  model_version_id: null,
  started_at: "2026-08-01T00:00:00Z",
  finished_at: "2026-08-01T00:20:00Z",
  created_at: "2026-08-01T00:00:00Z",
};

describe("vision training run page", () => {
  it("shows advanced metrics and preserves a deep link back to the train tab", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity } },
    });
    client.setQueryData(visionKeys.training("run-1"), failedRun);

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/dashboard/agriculture/vision-models/training-runs/run-1"]}>
          <Routes>
            <Route
              path="/dashboard/agriculture/vision-models/training-runs/:runId"
              element={<VisionTrainingRunPage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Model evaluation failed.")).toBeVisible();
    expect(screen.getByText("Training loss")).toBeVisible();
    expect(screen.getByText("1.2000")).toBeVisible();
    expect(screen.getByText("Evaluation failed")).toBeVisible();
    expect(screen.getByRole("link", { name: /training runs/i })).toHaveAttribute(
      "href",
      "/dashboard/agriculture/vision-models?project=project-1&tab=train",
    );
  });
});
