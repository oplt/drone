import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { AgricultureAnalysisRun } from "../types";
import { AgricultureAnalyticsExpansionPanel } from "./AgricultureAnalyticsExpansionPanel";

vi.mock("../hooks", () => ({
  useAgricultureSpatialLayers: () => ({
    data: {
      layers: [
        { layer: "stand_gap", status: "ready", summary: { count: 2, area_m2: 8, assumptions: { crop_type: "corn", expected_plant_spacing_m: .5 } } },
        { layer: "plant_spacing", status: "ready", summary: { median_spacing_m: .51, dispersion_iqr_m: .04, sample_count: 20, statistical_outlier_count: 2 } },
        { layer: "weed_density", status: "ready", summary: { field_density_detections_per_m2: .0123, hotspot_count: 3, cell_size_m: 10 } },
      ],
    },
    isError: false,
  }),
  useAgricultureAnalysisReadiness: () => ({
    data: {
      capabilities: [
        { id: "ripeness_classification", label: "Crop-specific ripeness classification", available: false, unavailable_reasons: ["A registered camera calibration is required."], limitations: ["Never generalizes to arbitrary RGB."] },
      ],
    },
  }),
}));

const run = {
  id: "run-1",
  flight_id: "flight-1",
  counters: {},
} as AgricultureAnalysisRun;

describe("AgricultureAnalyticsExpansionPanel", () => {
  it("shows operational metric summaries and crop-specific release limits", () => {
    render(<AgricultureAnalyticsExpansionPanel run={run} />);
    expect(screen.getByText(/2 gaps · affected area 8.00 m²/i)).toBeTruthy();
    expect(screen.getByText(/0.0123 detections\/m²/i)).toBeTruthy();
    expect(screen.getByText(/registered camera calibration is required/i)).toBeTruthy();
    expect(screen.getByText(/research experiment not evaluated/i)).toBeTruthy();
  });
});
