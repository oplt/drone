import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgricultureInferenceReuseNotice } from "./AgricultureInferenceReuseNotice";

describe("AgricultureInferenceReuseNotice", () => {
  it("renders nothing when no inference was reused", () => {
    const { container } = render(
      <AgricultureInferenceReuseNotice
        reuse={{
          run_input_checksum: "abc",
          reused_job_count: 0,
          total_job_count: 1,
          fully_reused: false,
          details: [],
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows reuse headline and prior run details", () => {
    render(
      <AgricultureInferenceReuseNotice
        reuse={{
          run_input_checksum: "sha256:input123456",
          reused_job_count: 1,
          total_job_count: 1,
          fully_reused: true,
          details: [
            {
              capability_id: "weed_detection",
              video_id: "video-1",
              video_job_id: "job-old",
              reused: true,
              reused_from_run_id: "run-old",
              source_checksum: "sha256:video123456",
              model_checksum: "sha256:model123456",
              vision_model_version_id: "version-1",
              inference_profile: { frame_stride_seconds: 1 },
              original_completed_at: "2026-08-01T12:00:00Z",
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByText(/Validated video inference reused for all sources/i),
    ).toBeVisible();
    expect(screen.getByText(/Prior run: run-old/i)).toBeVisible();
    expect(screen.getByText(/No reprocessing of identical validated inputs/i)).toBeVisible();
  });
});
