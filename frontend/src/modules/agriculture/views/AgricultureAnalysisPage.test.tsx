import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import AgricultureAnalysisPage from "./AgricultureAnalysisPage";

vi.mock("../hooks", () => ({
  useAgricultureAnalysisRun: () => ({
    data: { id: "run-1", flight_id: "flight-1", status: "completed", progress: 100, error: null },
    isLoading: false,
    isError: false,
  }),
  useAgricultureAnalysisQuality: () => ({ data: { stages: [] } }),
  useReplayAgricultureAnalysisRun: () => ({ mutate: vi.fn(), isPending: false }),
  useRetryAgricultureAnalysisStage: () => ({ mutate: vi.fn(), isPending: false, variables: null }),
}));

vi.mock("../components/PrioritizedFindingsPanel", () => ({ PrioritizedFindingsPanel: () => <div>Prioritized findings queue</div> }));
vi.mock("../components/AgricultureReportPanel", () => ({ AgricultureReportPanel: () => <div>Findings map</div> }));
vi.mock("../components/AgricultureReviewWorkspace", () => ({ AgricultureReviewWorkspace: () => <div>Review queue</div> }));
vi.mock("../components/AgricultureMediaTimelinePanel", () => ({ AgricultureMediaTimelinePanel: () => <div>Media timeline</div> }));
vi.mock("../components/AgricultureSensorFusionPanel", () => ({ AgricultureSensorFusionPanel: () => <div>Sensor fusion</div> }));
vi.mock("../components/AgricultureSensorCalibrationWizard", () => ({ AgricultureSensorCalibrationWizard: () => <div>Calibration</div> }));
vi.mock("../components/AgricultureModelRegistryPanel", () => ({ AgricultureModelRegistryPanel: () => <div>Models</div> }));
vi.mock("../components/AgricultureCropInsightsPanel", () => ({ AgricultureCropInsightsPanel: () => <div>Insights</div> }));
vi.mock("../components/AgricultureActionExportPanel", () => ({ AgricultureActionExportPanel: () => <div>Actions</div> }));
vi.mock("../components/AgricultureGovernanceAssistantPanel", () => ({ AgricultureGovernanceAssistantPanel: () => <div>Governance details</div> }));
vi.mock("../components/AnalysisRunProgress", () => ({ AnalysisRunProgress: () => <div>Analysis complete</div> }));

describe("AgricultureAnalysisPage", () => {
  it("defaults to findings and places technical content behind a tab", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/dashboard/agriculture/analysis/run-1"]}>
        <Routes>
          <Route path="/dashboard/agriculture/analysis/:runId" element={<AgricultureAnalysisPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Prioritized findings queue")).toBeInTheDocument();
    expect(screen.getByText("Findings map")).toBeInTheDocument();
    expect(screen.queryByText("Calibration")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Advanced" }));
    expect(screen.getByText("Governance details")).toBeInTheDocument();
    expect(screen.queryByText("Findings map")).not.toBeInTheDocument();
    await user.click(screen.getByText("Calibration & model registry"));
    expect(screen.getByText("Calibration")).toBeInTheDocument();
  });
});
