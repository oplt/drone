import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { visionKeys } from "../../agriculture/hooks/useVisionModels";
import type { VisionModelVersion } from "../../agriculture/visionTypes";
import {
  AnalysisInferenceSection,
  type AnalysisControlsProps,
} from "./AnalysisControls";

function renderControls(overrides: Partial<AnalysisControlsProps> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData<VisionModelVersion[]>(visionKeys.models(), [
    {
      id: "model-version-1",
      model_id: "model-1",
      project_id: "project-1",
      training_run_id: "run-1",
      dataset_id: "dataset-1",
      name: "Tomato ripeness",
      crop: "tomato",
      task_type: "detection",
      capability_id: "object_detection",
      version: 3,
      architecture: "yolo26s.pt",
      status: "production",
      classes: ["ripe", "unripe"],
      metrics: {},
      created_at: "2026-08-01T00:00:00Z",
    },
  ]);
  const onPayload = vi.fn();
  const props: AnalysisControlsProps = {
    file: null,
    video: null,
    payload: {
      model_name: "yolo26s.pt",
      model_version_id: null,
      frame_stride_seconds: 1,
      confidence_threshold: 0.35,
      tracking_enabled: false,
      small_object_mode: false,
    },
    uploading: false,
    starting: false,
    onFile: vi.fn(),
    onPayload,
    onUpload: vi.fn(),
    onAnalyze: vi.fn(),
    ...overrides,
  };
  render(
    <QueryClientProvider client={client}>
      <AnalysisInferenceSection {...props} />
    </QueryClientProvider>,
  );
  return { onPayload, props };
}

describe("video analysis agricultural options", () => {
  it("offers tracking and small-object mode with clear impact text", () => {
    const { onPayload, props } = renderControls();

    fireEvent.click(screen.getByRole("switch", { name: /track objects/i }));
    expect(onPayload).toHaveBeenCalledWith(
      expect.objectContaining({
        tracking_enabled: true,
        tracker_type: "bytetrack",
      }),
    );

    fireEvent.click(
      screen.getByRole("switch", { name: /small-object mode/i }),
    );
    expect(onPayload).toHaveBeenCalledWith(
      expect.objectContaining({ ...props.payload, small_object_mode: true }),
    );
    expect(screen.getByText(/slower sliced inference/i)).toBeVisible();
  });

  it("shows a production agricultural model in the selector", () => {
    renderControls({
      payload: {
        model_name: "yolo26s.pt",
        model_version_id: "model-version-1",
        frame_stride_seconds: 1,
        confidence_threshold: 0.35,
      },
    });
    expect(screen.getByText(/Tomato ripeness · v3 · tomato/i)).toBeVisible();
  });
});
