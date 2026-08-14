import { describe, expect, it } from "vitest";
import {
  buildBreadcrumbTrail,
  toBreadcrumbLabel,
  truncateIdLabel,
} from "./breadcrumbTrail";

describe("NavbarBreadcrumbs trail", () => {
  it("labels workspace overview", () => {
    expect(buildBreadcrumbTrail("/dashboard")).toEqual([
      { label: "Overview", to: "/dashboard", current: true },
    ]);
  });

  it("maps primary IA destinations", () => {
    const cases: Array<[string, string[]]> = [
      ["/dashboard/field", ["Overview", "Missions"]],
      ["/dashboard/agriculture/fields", ["Overview", "Agriculture", "Fields"]],
      ["/dashboard/agriculture/vision-models", ["Overview", "Agriculture", "Datasets & Training"]],
      ["/dashboard/property-patrol", ["Overview", "Property Inspection"]],
      ["/dashboard/warehouse", ["Overview", "Warehouse"]],
      ["/dashboard/photogrammetry", ["Overview", "Photogrammetry"]],
      ["/dashboard/animalfarm", ["Overview", "Animal Farm"]],
      ["/dashboard/controlled", ["Overview", "Live Operations"]],
      ["/dashboard/video-analysis", ["Overview", "Video Analysis"]],
      ["/dashboard/insights", ["Overview", "History"]],
      ["/dashboard/observability", ["Overview", "Observability"]],
      ["/dashboard/fleet", ["Overview", "Fleet"]],
      ["/dashboard/templates", ["Overview", "Automations"]],
      ["/dashboard/account", ["Overview", "Account"]],
      ["/dashboard/settings", ["Overview", "Settings"]],
    ];

    for (const [path, labels] of cases) {
      expect(buildBreadcrumbTrail(path).map((c) => c.label)).toEqual(labels);
    }
  });

  it("truncates deep field/flight/run ids", () => {
    const trail = buildBreadcrumbTrail(
      "/dashboard/agriculture/fields/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/extra",
    );
    expect(trail.map((c) => c.label)).toEqual([
      "Overview",
      "Agriculture",
      "Fields",
      "aaaaaaaa…",
      "Extra",
    ]);
  });

  it("handles legacy observability alias", () => {
    expect(buildBreadcrumbTrail("/observability").map((c) => c.label)).toEqual([
      "Overview",
      "Observability",
    ]);
  });

  it("truncates long ids in toBreadcrumbLabel", () => {
    expect(toBreadcrumbLabel("field")).toBe("Missions");
    expect(truncateIdLabel("1234567890abcdef")).toBe("12345678…");
  });
});
