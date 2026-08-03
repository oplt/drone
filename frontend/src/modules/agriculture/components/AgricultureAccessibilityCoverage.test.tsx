import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { AgricultureAccessibilityBoundary } from "./AgricultureAccessibilityBoundary";
import { ExportApprovalDialog } from "./ExportApprovalDialog";
import { FlightQualityPanel } from "./FlightQualityPanel";
import { ObservationMap } from "./ObservationMap";

const geojson = {
  features: [{
    type: "Feature",
    geometry: { type: "Point", coordinates: [4, 50] },
    properties: { id: "obs-1", observation_type: "weed", severity: 0.9 },
  }],
};

describe("agriculture WCAG interaction coverage", () => {
  it("supports keyboard map/list review without color-only meaning", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<AgricultureAccessibilityBoundary><ObservationMap geojson={geojson} onSelect={onSelect} /></AgricultureAccessibilityBoundary>);
    const feature = screen.getByRole("button", { name: /Select weed obs-1/i });
    feature.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("obs-1");
    expect(screen.getAllByText(/High severity/i).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Map severity legend")).toBeVisible();
  });

  it("keeps dialog, status and legends accessible", async () => {
    const user = userEvent.setup();
    const { container } = render(<AgricultureAccessibilityBoundary>
      <FlightQualityPanel quality={{ status: "warning" }} coverage={{ status: "pass" }} />
      <ExportApprovalDialog exports={[]} pending={false} error={false} onGenerate={vi.fn()} onDownload={vi.fn()} />
    </AgricultureAccessibilityBoundary>);
    await user.click(screen.getByRole("button", { name: "Generate export" }));
    expect(screen.getByRole("dialog", { name: "Approve export request" })).toBeVisible();
    expect(document.querySelector('[role="status"]')).toHaveTextContent(/Quality: warning/i);
    expect(await axe(container)).toHaveNoViolations();
  });
});
