import { describe, expect, it } from "vitest";
import {
  formatInferenceReuseHeadline,
  hasReusedInference,
} from "./inferenceReuseDisplay";

describe("inferenceReuseDisplay", () => {
  it("detects reused inference", () => {
    expect(
      hasReusedInference({
        run_input_checksum: null,
        reused_job_count: 2,
        total_job_count: 3,
        fully_reused: false,
        details: [],
      }),
    ).toBe(true);
  });

  it("formats partial reuse headline", () => {
    expect(
      formatInferenceReuseHeadline({
        run_input_checksum: null,
        reused_job_count: 2,
        total_job_count: 3,
        fully_reused: false,
        details: [],
      }),
    ).toBe("Validated video inference reused for 2 of 3 sources.");
  });
});
