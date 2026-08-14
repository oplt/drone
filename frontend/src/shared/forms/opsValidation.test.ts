import { describe, expect, it } from "vitest";
import {
  agriculturePlannerSchema,
  isValidCronExpression,
} from "./opsValidation";

describe("agriculturePlannerSchema", () => {
  it("accepts safe altitude and overlap", async () => {
    await expect(
      agriculturePlannerSchema.validate({
        altitude: 40,
        rowSpacing: 8,
        gridAngle: 0,
        safetyInset: 2,
        front_overlap_pct: 75,
        side_overlap_pct: 65,
      }),
    ).resolves.toBeTruthy();
  });

  it("rejects unsafe altitude and overlap with field messages", async () => {
    await expect(
      agriculturePlannerSchema.validate(
        {
          altitude: 2,
          rowSpacing: 8,
          gridAngle: 0,
          safetyInset: 2,
          front_overlap_pct: 20,
          side_overlap_pct: 10,
        },
        { abortEarly: false },
      ),
    ).rejects.toMatchObject({
      inner: expect.arrayContaining([
        expect.objectContaining({ path: "altitude" }),
        expect.objectContaining({ path: "front_overlap_pct" }),
        expect.objectContaining({ path: "side_overlap_pct" }),
      ]),
    });
  });
});

describe("isValidCronExpression", () => {
  it("allows empty (manual-only) and common 5-field cron", () => {
    expect(isValidCronExpression("")).toBe(true);
    expect(isValidCronExpression("0 6 * * 1")).toBe(true);
    expect(isValidCronExpression("*/15 * * * *")).toBe(true);
  });

  it("rejects malformed cron", () => {
    expect(isValidCronExpression("not cron")).toBe(false);
    expect(isValidCronExpression("0 6 * *")).toBe(false);
    expect(isValidCronExpression("60 6 * * 1")).toBe(false);
  });
});
