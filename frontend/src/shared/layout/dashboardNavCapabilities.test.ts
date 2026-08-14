import { describe, expect, it } from "vitest";
import {
  capabilitiesForRole,
  hasNavCapability,
} from "./dashboardNavCapabilities";
import {
  filterDashboardNavigation,
  isApplicationsRoute,
} from "./dashboardNavigation";

describe("dashboardNavCapabilities", () => {
  it("maps viewer to read-only destinations", () => {
    expect(hasNavCapability("viewer", "operations.history")).toBe(true);
    expect(hasNavCapability("viewer", "operations.missions")).toBe(false);
    expect(hasNavCapability("viewer", "applications.agriculture")).toBe(true);
    expect(hasNavCapability("viewer", "admin.system")).toBe(false);
  });

  it("maps pilot to operations and flight surfaces", () => {
    expect(hasNavCapability("pilot", "operations.live")).toBe(true);
    expect(hasNavCapability("pilot", "applications.agriculture")).toBe(false);
    expect(hasNavCapability("pilot", "ai.datasets")).toBe(false);
  });

  it("maps operator to agriculture review and automations", () => {
    expect(hasNavCapability("operator", "applications.agriculture")).toBe(true);
    expect(hasNavCapability("operator", "ai.automations")).toBe(true);
    expect(hasNavCapability("operator", "admin.system")).toBe(false);
  });

  it("maps org_admin to administration destinations", () => {
    expect(hasNavCapability("org_admin", "admin.system")).toBe(true);
    expect(hasNavCapability("org_admin", "admin.panel")).toBe(true);
  });
});

describe("filterDashboardNavigation", () => {
  it("hides empty sections for the active role", () => {
    const viewerSections = filterDashboardNavigation("viewer");
    expect(viewerSections.map((section) => section.label)).toEqual([
      "Workspace",
      "Operations",
      "Applications",
      "AI & Models",
    ]);
    const labels = viewerSections.flatMap((section) =>
      section.entries.flatMap((entry) =>
        entry.children?.map((child) => child.text) ?? (entry.text ? [entry.text] : []),
      ),
    );
    expect(labels.includes("Missions")).toBe(false);
  });

  it("keeps agriculture visible for reviewer-like operator roles", () => {
    const operatorSections = filterDashboardNavigation("operator");
    const applicationChildren = operatorSections
      .find((section) => section.label === "Applications")
      ?.entries.flatMap((entry) => entry.children ?? []);
    expect(applicationChildren?.some((entry) => entry.text === "Agriculture")).toBe(true);
  });

  it("filters application route detection to visible children", () => {
    const viewerSections = filterDashboardNavigation("viewer");
    expect(isApplicationsRoute("/dashboard/agriculture/fields", viewerSections)).toBe(true);
    expect(isApplicationsRoute("/dashboard/property-patrol", viewerSections)).toBe(false);
  });

  it("defaults unknown roles to operator capabilities", () => {
    expect(capabilitiesForRole("custom-role")).toEqual(capabilitiesForRole("operator"));
  });
});
