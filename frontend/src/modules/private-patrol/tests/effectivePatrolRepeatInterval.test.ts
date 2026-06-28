import { describe, expect, it } from "vitest";
import {
  DEFAULT_PATROL_GRID_PARAMS,
  effectivePatrolRepeatIntervalMinutes,
} from "../types";

describe("effectivePatrolRepeatIntervalMinutes", () => {
  it("returns 0 when both repeat and start delay are unset", () => {
    expect(
      effectivePatrolRepeatIntervalMinutes({
        repeat_interval_minutes: 0,
        start_after_minutes: 0,
      }),
    ).toBe(0);
  });

  it("uses repeat when explicitly set", () => {
    expect(
      effectivePatrolRepeatIntervalMinutes({
        repeat_interval_minutes: 5,
        start_after_minutes: 1,
      }),
    ).toBe(5);
  });

  it("falls back to start delay when repeat is 0", () => {
    expect(
      effectivePatrolRepeatIntervalMinutes({
        repeat_interval_minutes: 0,
        start_after_minutes: 1,
      }),
    ).toBe(1);
  });

  it("matches default patrol params", () => {
    expect(effectivePatrolRepeatIntervalMinutes(DEFAULT_PATROL_GRID_PARAMS)).toBe(0);
  });
});
