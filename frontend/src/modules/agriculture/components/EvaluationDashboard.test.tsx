import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { visionKeys } from "../hooks/useVisionModels";
import type { ModelEvaluation, VisionModelVersion } from "../visionTypes";
import { EvaluationDashboard } from "./EvaluationDashboard";

vi.mock("@mui/x-charts/BarChart", () => ({
  BarChart: () => <div data-testid="performance-chart" />,
}));

const version: VisionModelVersion = {
  id: "version-4",
  model_id: "model-1",
  project_id: "project-1",
  training_run_id: "run-4",
  dataset_id: "dataset-2",
  name: "Tomato ripeness",
  crop: "tomato",
      task_type: "detection",
      capability_id: "object_detection",
  version: 4,
  architecture: "yolo26s.pt",
  status: "candidate",
  classes: ["ripe_tomato", "damaged_tomato"],
  metrics: { summary: { map50: 0.913 } },
  created_at: "2026-08-01T00:00:00Z",
};

const evaluation: ModelEvaluation = {
  model_version_id: version.id,
  model_name: version.name,
  version: 4,
  state: "completed",
  metrics: {},
  summary: {
    precision: 0.928,
    recall: 0.871,
    f1: 0.898,
    map50: 0.913,
    map75: 0.781,
    map50_95: 0.683,
  },
  per_class: [
    {
      class_index: 0,
      class_name: "ripe_tomato",
      precision: 0.95,
      recall: 0.9,
      f1: 0.924,
      map50: 0.94,
      map75: 0.8,
      map50_95: 0.72,
    },
  ],
  confusion_matrix: [
    [8, 1],
    [2, 7],
  ],
  confusion_matrix_labels: ["ripe_tomato", "background"],
  dataset_id: "dataset-2",
  dataset_version: 2,
  dataset_image_count: 420,
  test_image_count: 63,
  dataset_checksum: "checksum",
  split: "test",
  image_size: 640,
  base_model: "yolo26s.pt",
  preset: "balanced",
  training_date: "2026-08-01T00:00:00Z",
  evaluated_at: "2026-08-01T01:00:00Z",
  artifacts: [],
};

describe("vision evaluation dashboard", () => {
  it("renders persisted summary and per-class metrics", () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
    client.setQueryData(visionKeys.evaluation(version.id), evaluation);
    render(
      <QueryClientProvider client={client}>
        <EvaluationDashboard version={version} allVersions={[version]} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("91.3%")).toBeVisible();
    expect(screen.getAllByText("92.8%").length).toBeGreaterThan(0);
    expect(screen.getByText("ripe tomato")).toBeVisible();
    expect(screen.getByTestId("performance-chart")).toBeVisible();
  });

  it("shows deployment replacement guardrails", () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
    client.setQueryData(visionKeys.evaluation(version.id), evaluation);
    const production: VisionModelVersion = {
      ...version,
      id: "version-3",
      version: 3,
      status: "production",
      metrics: { summary: { map50: 0.884 } },
    };
    render(
      <QueryClientProvider client={client}>
        <EvaluationDashboard
          version={version}
          allVersions={[version, production]}
        />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /deploy candidate/i }));
    expect(screen.getByText(/replaces production v3/i)).toBeVisible();
    expect(screen.getByText(/Current production mAP50/i)).toBeVisible();
  });
});
