import { describe, expect, it } from "vitest";
import {
  buildAnalysisRunStatusPresentation,
  buildQualityGatePresentation,
  extractQualityBlockReason,
  formatAnalysisRunProgress,
  formatAnalysisStatusLabel,
  isAnalysisRunReplayable,
  isAnalysisStageRetryable,
} from "./analysisRunStatusPresentation";

describe("analysis run status presentation", () => {
  it("maps run statuses to consistent labels and chip colors", () => {
    expect(formatAnalysisStatusLabel("waiting_inference")).toBe(
      "Waiting for inference",
    );
    expect(formatAnalysisStatusLabel("blocked_quality")).toBe(
      "Blocked by quality gate",
    );

    const running = buildAnalysisRunStatusPresentation({
      status: "running",
      progress: 0.42,
    });
    expect(running.label).toBe("Running");
    expect(running.chipColor).toBe("info");
    expect(running.summaryLine).toBe("Running · 42%");
    expect(running.isActive).toBe(true);
    expect(running.isTerminal).toBe(false);
  });

  it("normalizes progress from ratio or percent", () => {
    expect(formatAnalysisRunProgress(0.4)).toBe(40);
    expect(formatAnalysisRunProgress(72)).toBe(72);
    expect(formatAnalysisRunProgress(Number.NaN)).toBe(0);
  });

  it("derives replay, cancellation, and retry semantics", () => {
    expect(isAnalysisRunReplayable("failed")).toBe(true);
    expect(isAnalysisRunReplayable("running")).toBe(false);

    const cancelled = buildAnalysisRunStatusPresentation({
      status: "cancelling",
      progress: 0.1,
    });
    expect(cancelled.isCancelling).toBe(true);
    expect(cancelled.isCancelled).toBe(false);

    expect(
      isAnalysisStageRetryable({
        status: "failed",
        retryable: true,
      }),
    ).toBe(true);
    expect(
      isAnalysisStageRetryable({
        status: "failed",
        retryable: false,
      }),
    ).toBe(false);
  });

  it("includes current stage, quality block reason, and last update", () => {
    const presentation = buildAnalysisRunStatusPresentation({
      status: "blocked_quality",
      progress: 35,
      error: "Image-quality gate blocked agricultural inference",
      retryCount: 2,
      qualityGate: {
        status: "blocked",
        reasons: ["blur", "exposure"],
      },
      createdAt: "2026-08-01T08:00:00Z",
      stages: [
        {
          id: "stage-1",
          stage_name: "quality_gate",
          status: "completed",
          progress: 100,
          finished_at: "2026-08-01T08:05:00Z",
        },
        {
          id: "stage-2",
          stage_name: "observation_aggregation",
          status: "queued",
          progress: 0,
          started_at: "2026-08-01T08:06:00Z",
        },
      ],
    });

    expect(presentation.qualityBlocked).toBe(true);
    expect(presentation.qualityBlockReason).toBe("blur, exposure");
    expect(presentation.currentStageLabel).toBe("observation aggregation");
    expect(presentation.lastUpdatedAt).toBe("2026-08-01T08:06:00Z");
    expect(presentation.retryCount).toBe(2);
    expect(presentation.isReplayable).toBe(true);
  });

  it("formats quality gate chips consistently", () => {
    expect(
      buildQualityGatePresentation({
        qualityGate: { status: "warning" },
      }),
    ).toEqual({
      label: "Warning",
      chipColor: "warning",
      blocked: false,
      reason: undefined,
    });

    expect(
      extractQualityBlockReason({
        status: "blocked_quality",
        qualityGate: { status: "blocked", reasons: ["no_quality_frames"] },
      }),
    ).toBe("no quality frames");
  });
});
