import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AgricultureTemporalWorkspace } from "./AgricultureTemporalWorkspace";

vi.mock("../hooks", () => ({
  useAgricultureTimeline: () => ({
    data: [{ id: "flight-1", status: "completed" }],
    isLoading: false,
  }),
  useAgricultureComparisons: () => ({ data: [] }),
  useComparableFlights: () => ({ data: [] }),
  useAgricultureFlight: () => ({ data: { profile_snapshot: {} } }),
  useAgricultureAnalysisRuns: () => ({ data: [] }),
  useAgricultureFieldPlans: () => ({ data: [] }),
  useCompareAgricultureFlight: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReviewAgricultureObservation: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateAgricultureAnnotation: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateAgricultureReportSnapshot: () => ({ mutate: vi.fn(), isPending: false }),
  useDuplicateAgriculturePlan: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("./AgricultureGeoJsonPreview", () => ({
  AgricultureGeoJsonPreview: () => <div>geojson</div>,
}));

vi.mock("./FlightTimeline", () => ({
  FlightTimeline: () => <div>timeline</div>,
}));

vi.mock("../../video-analysis/evidenceSelection", () => ({
  selectDetectionEvidence: vi.fn(),
}));

describe("AgricultureTemporalWorkspace compare gate", () => {
  it("blocks comparison when fewer than two flights exist", () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <AgricultureTemporalWorkspace fieldId={1} currentFlightId="flight-1" />
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(
      screen.getByText(/second quality-approved flight is required/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Compare flights/i })).not.toBeInTheDocument();
  });
});
