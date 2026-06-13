import { describe, expect, it } from "vitest";
import { buildGrafanaUrl } from "./urlBuilders";

describe("buildGrafanaUrl", () => {
  it("adds org, time, drone, and mission params with encoding", () => {
    const result = buildGrafanaUrl("https://grafana.example.com/d/drone-fleet/fleet-health", {
      droneId: "DRONE 001",
      missionId: "MISSION/123",
      from: "now-6h",
      to: "now",
      orgId: 2,
    });

    const url = new URL(result);
    expect(url.searchParams.get("orgId")).toBe("2");
    expect(url.searchParams.get("from")).toBe("now-6h");
    expect(url.searchParams.get("to")).toBe("now");
    expect(url.searchParams.get("var-drone_id")).toBe("DRONE 001");
    expect(url.searchParams.get("var-mission_id")).toBe("MISSION/123");
  });

  it("omits optional IDs when missing", () => {
    const result = buildGrafanaUrl("https://grafana.example.com/explore");
    const url = new URL(result);

    expect(url.searchParams.get("orgId")).toBe("1");
    expect(url.searchParams.get("from")).toBe("now-1h");
    expect(url.searchParams.get("to")).toBe("now");
    expect(url.searchParams.has("var-drone_id")).toBe(false);
    expect(url.searchParams.has("var-mission_id")).toBe(false);
  });
});
