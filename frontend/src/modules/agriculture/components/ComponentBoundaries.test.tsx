import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import {
  AgricultureFieldProfile,
  AgricultureFlightPlanner,
  AnalysisRunProgress,
  CoverageMapLayer,
  EvidenceFrameCarousel,
  ExportApprovalDialog,
  FlightQualityPanel,
  FlightTimeline,
  HealthLayerSwitcher,
  InspectionActionPanel,
  ObservationMap,
  ObservationReviewDrawer,
  SensorCalibrationPanel,
} from "../index";
import { AgricultureAccessibilityBoundary } from "./AgricultureAccessibilityBoundary";
import { agricultureAccessibilityStyles } from "./accessibilityStyles";

describe("agriculture component boundaries", () => {
  it("exports every required independently addressable boundary", () => {
    [
      AgricultureFieldProfile,
      AgricultureFlightPlanner,
      FlightQualityPanel,
      CoverageMapLayer,
      HealthLayerSwitcher,
      ObservationMap,
      ObservationReviewDrawer,
      EvidenceFrameCarousel,
      FlightTimeline,
      AnalysisRunProgress,
      SensorCalibrationPanel,
      InspectionActionPanel,
      ExportApprovalDialog,
    ].forEach((component) => expect(component).toBeTypeOf("function"));
  });

  it("exposes accessible quality, layer, progress and timeline controls", () => {
    render(
      <MemoryRouter>
        <FlightQualityPanel
          quality={{ status: "blocked" }}
          coverage={{ status: "warning" }}
        />
        <HealthLayerSwitcher
          layer="all"
          onLayerChange={vi.fn()}
          confidence={0.5}
          onConfidenceChange={vi.fn()}
          severity={0.2}
          onSeverityChange={vi.fn()}
        />
        <AnalysisRunProgress status="running" progress={0.4} />
        <FlightTimeline
          flights={[
            {
              id: "f1",
              created_at: "2026-08-01T00:00:00Z",
              status: "captured",
              quality_summary: {},
              coverage_summary: {},
            },
          ]}
          value={0}
          onChange={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Quality gate blocked inference/i)).toBeVisible();
    expect(
      screen.getByRole("combobox", { name: "Health layer" }),
    ).toBeVisible();
    expect(
      screen.getByRole("progressbar", { name: "Analysis progress" }),
    ).toBeVisible();
    expect(
      screen.getByRole("slider", { name: "Flight timeline" }),
    ).toBeVisible();
  });

  it("requires an explicit export approval interaction", async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn();
    render(
      <ExportApprovalDialog
        exports={[]}
        pending={false}
        error={false}
        onGenerate={onGenerate}
        onDownload={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Generate export" }));
    expect(
      screen.getByRole("dialog", { name: "Approve export request" }),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Approve and generate" }),
    );
    expect(onGenerate).toHaveBeenCalledWith("report", "geojson");
  });

  it("defines visible focus, reduced motion and responsive touch targets", () => {
    expect(
      agricultureAccessibilityStyles[".agriculture-surface :focus-visible"]
        .outline,
    ).toBe("3px solid #174ea6");
    const touch =
      agricultureAccessibilityStyles[
        "@media (pointer: coarse), (max-width: 767px)"
      ];
    expect(
      Object.values(touch).every((rule) => rule.minHeight === "44px"),
    ).toBe(true);
    const reduced =
      agricultureAccessibilityStyles["@media (prefers-reduced-motion: reduce)"];
    expect(Object.values(reduced)[0].transitionDuration).toBe(
      "0.01ms !important",
    );
  });

  it("has no automated WCAG violations in representative controls", async () => {
    const { container } = render(
      <AgricultureAccessibilityBoundary>
        <FlightQualityPanel
          quality={{ status: "warning" }}
          coverage={{ status: "partial" }}
        />
        <HealthLayerSwitcher
          layer="all"
          onLayerChange={vi.fn()}
          confidence={0.5}
          onConfidenceChange={vi.fn()}
          severity={0.2}
          onSeverityChange={vi.fn()}
        />
        <AnalysisRunProgress status="running" progress={0.4} />
        <SensorCalibrationPanel
          status={{
            flight_id: "f1",
            inventory: ["rgb"],
            spectral: { status: "not_required" },
            calibration_ids: [],
            readings: {},
            status: "pass",
          }}
        />
      </AgricultureAccessibilityBoundary>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
