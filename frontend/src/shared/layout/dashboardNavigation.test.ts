import { describe, expect, it } from "vitest";
import {
  filterDashboardNavigation,
  isApplicationsRoute,
} from "./dashboardNavigation";

describe("dashboardNavigation", () => {
  it("groups primary destinations under product sections", () => {
    expect(filterDashboardNavigation("admin").map((section) => section.label)).toEqual([
      "Workspace",
      "Operations",
      "Applications",
      "AI & Models",
      "Administration",
    ]);
  });

  it("detects application routes for nested selection", () => {
    const sections = filterDashboardNavigation("operator");
    expect(isApplicationsRoute("/dashboard/agriculture/fields", sections)).toBe(true);
    expect(isApplicationsRoute("/dashboard/warehouse/live", sections)).toBe(true);
    expect(isApplicationsRoute("/dashboard/fleet", sections)).toBe(false);
  });
});
