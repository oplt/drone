import { describe, expect, it } from "vitest";
import { deriveAgricultureJourneyStage } from "../journeyState";

describe("deriveAgricultureJourneyStage", () => {
  it.each([
    [{ flightStatus: "flying" }, 0],
    [{ flightStatus: "completed" }, 1],
    [{ flightStatus: "completed", analysisStatus: "running" }, 2],
    [{ flightStatus: "completed", analysisStatus: "completed" }, 3],
    [{ flightStatus: "completed", analysisStatus: "completed", reviewComplete: true }, 4],
  ] as const)("derives the authoritative journey stage", (input, expected) => {
    expect(deriveAgricultureJourneyStage(input)).toBe(expected);
  });
});
