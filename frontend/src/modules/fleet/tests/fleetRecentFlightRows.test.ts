import { describe, expect, it } from "vitest";
import {
  mapRecentFlightRows,
  normalizeFleetFlightStatus,
} from "../utils/fleetRecentFlightRows";

describe("fleetRecentFlightRows characterization", () => {
  it("normalizes backend flight statuses for the fleet grid", () => {
    expect(normalizeFleetFlightStatus("in_progress")).toBe("Active");
    expect(normalizeFleetFlightStatus("paused")).toBe("Paused");
    expect(normalizeFleetFlightStatus("aborted")).toBe("Interrupted");
    expect(normalizeFleetFlightStatus("failed")).toBe("Failed");
    expect(normalizeFleetFlightStatus("completed")).toBe("Completed");
  });

  it("maps recent flights into grid rows with formatted duration and distance", () => {
    expect(
      mapRecentFlightRows([
        {
          id: 1,
          name: "North patrol",
          status: "running",
          duration_min: 95,
          distance_km: 12.34,
          telemetry_points: 420,
          started_at: "2026-08-14T10:15:00Z",
        },
      ]),
    ).toEqual([
      {
        id: 1,
        plan: "North patrol",
        status: "Active",
        duration: "1h 35m",
        distance: "12.3 km",
        telemetry_points: 420,
        started_at: expect.any(String),
      },
    ]);
  });
});
