import { describe, expect, it } from "vitest";
import {
  buildBreadcrumbTrail,
  toBreadcrumbLabel,
  truncateIdLabel,
} from "./breadcrumbTrail";

describe("NavbarBreadcrumbs trail", () => {
  it("labels Operations hub overview", () => {
    expect(buildBreadcrumbTrail("/dashboard")).toEqual([
      { label: "Operations Hub", to: "/dashboard", current: true },
    ]);
  });

  it("maps primary IA destinations", () => {
    const cases: Array<[string, string[]]> = [
      ["/dashboard/field", ["Operations Hub", "Field Survey"]],
      ["/dashboard/agriculture/fields", ["Operations Hub", "Agriculture", "Fields"]],
      ["/dashboard/agriculture/vision-models", ["Operations Hub", "Agriculture", "Vision Models"]],
      ["/dashboard/property-patrol", ["Operations Hub", "Property Patrol"]],
      ["/dashboard/warehouse", ["Operations Hub", "Warehouse"]],
      ["/dashboard/photogrammetry", ["Operations Hub", "Photogrammetry"]],
      ["/dashboard/animalfarm", ["Operations Hub", "Animal Farm"]],
      ["/dashboard/controlled", ["Operations Hub", "Controlled Flight"]],
      ["/dashboard/video-analysis", ["Operations Hub", "Video Analysis"]],
      ["/dashboard/insights", ["Operations Hub", "Insights"]],
      ["/dashboard/observability", ["Operations Hub", "Observability"]],
      ["/dashboard/fleet", ["Operations Hub", "Fleet"]],
      ["/dashboard/templates", ["Operations Hub", "Templates"]],
      ["/dashboard/account", ["Operations Hub", "Account"]],
      ["/dashboard/settings", ["Operations Hub", "Settings"]],
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
      "Operations Hub",
      "Agriculture",
      "Fields",
      "aaaaaaaa…",
      "Extra",
    ]);
  });

  it("handles legacy observability alias", () => {
    expect(buildBreadcrumbTrail("/observability").map((c) => c.label)).toEqual([
      "Operations Hub",
      "Observability",
    ]);
  });

  it("truncates long ids in toBreadcrumbLabel", () => {
    expect(toBreadcrumbLabel("field")).toBe("Field Survey");
    expect(truncateIdLabel("1234567890abcdef")).toBe("12345678…");
  });
});
