import { describe, expect, it } from "vitest";
import { legBearingDeg, legDistanceM } from "../utils/missionWaypointGeometry";

describe("MissionWaypointList geometry", () => {
  it("computes leg distance and bearing", () => {
    const a = { lat: 0, lon: 0, alt: 10 };
    const b = { lat: 0, lon: 0.001, alt: 10 };
    const distance = legDistanceM(a, b);
    expect(distance).toBeGreaterThan(100);
    expect(distance).toBeLessThan(120);
    const bearing = legBearingDeg(a, b);
    expect(bearing).toBeGreaterThan(80);
    expect(bearing).toBeLessThan(100);
  });
});
