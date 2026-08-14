import { describe, expect, it } from "vitest";
import {
  ANALYSIS_REVIEW_EVIDENCE,
  ANALYSIS_REVIEW_OPEN,
  readAnalysisReviewState,
  writeObservationSelection,
} from "./analysisReviewState";

describe("analysisReviewState", () => {
  it("reads observation and review focus from search params", () => {
    const params = new URLSearchParams("observation=obs-1&review=evidence");
    expect(readAnalysisReviewState(params)).toEqual({
      observationId: "obs-1",
      reviewOpen: true,
      focusEvidence: true,
    });
  });

  it("writes observation selection and clears review state", () => {
    const params = new URLSearchParams("layer=all&review=evidence");
    const next = writeObservationSelection(params, "obs-2", { review: false });
    expect(next.get("observation")).toBe("obs-2");
    expect(next.get("review")).toBeNull();
    expect(next.get("layer")).toBe("all");
  });

  it("writes review drawer modes", () => {
    const params = new URLSearchParams();
    expect(
      writeObservationSelection(params, "obs-3", { review: ANALYSIS_REVIEW_OPEN }).get("review"),
    ).toBe(ANALYSIS_REVIEW_OPEN);
    expect(
      writeObservationSelection(params, "obs-3", { review: ANALYSIS_REVIEW_EVIDENCE }).get("review"),
    ).toBe(ANALYSIS_REVIEW_EVIDENCE);
  });
});
