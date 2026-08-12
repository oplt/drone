import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalysisResultsSection } from "./AnalysisStatus";
import type { VideoAnalysisJob } from "../types";

function job(overrides: Partial<VideoAnalysisJob> = {}): VideoAnalysisJob {
  return {
    id: "job-1",
    video_id: "video-1",
    status: "failed",
    model_name: "yolo26s.pt",
    model_version: "registered:version-1:abc",
    frame_stride_seconds: 1,
    confidence_threshold: 0.35,
    tracking_enabled: false,
    tracker_type: "bytetrack",
    small_object_mode: false,
    progress: 42,
    error: "Analysis worker heartbeat expired. Retry the analysis.",
    terminal_reason_code: "WORKER_LEASE_EXPIRED",
    terminal_stage: "worker_lease",
    created_at: "2026-08-12T00:00:00Z",
    ...overrides,
  };
}

describe("AnalysisResultsSection terminal states", () => {
  it("explains stale worker leases with an actionable retry message", () => {
    render(<AnalysisResultsSection job={job()} detectionCount={0} />);
    expect(screen.getByText(/Failed during worker lease/i)).toBeVisible();
    expect(
      screen.getByText(/worker stopped reporting progress/i),
    ).toBeVisible();
  });

  it("explains all-frame inference failure instead of reporting success", () => {
    render(
      <AnalysisResultsSection
        job={job({
          error: "No video frames were successfully analyzed.",
          terminal_reason_code: "NO_SUCCESSFUL_FRAMES",
          terminal_stage: "inference",
        })}
        detectionCount={0}
      />,
    );
    expect(screen.getByText(/Failed during inference/i)).toBeVisible();
    expect(screen.getByText(/No sampled frame completed inference/i)).toBeVisible();
  });

  it("keeps cancel available while a job is still running", () => {
    const onCancel = vi.fn();
    render(
      <AnalysisResultsSection
        job={job({ status: "running", error: null, terminal_reason_code: null })}
        detectionCount={3}
        onCancel={onCancel}
      />,
    );
    screen.getByRole("button", { name: /Cancel analysis/i }).click();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
