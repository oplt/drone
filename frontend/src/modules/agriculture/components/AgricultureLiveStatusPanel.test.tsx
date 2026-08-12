import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AgricultureLiveStatusPanel } from "./AgricultureLiveStatusPanel";

vi.mock("../hooks", () => ({
  useAgricultureFlight: () => ({ data: { status: "completed", field_id: 2 }, isLoading: false, isError: false }),
  useAgricultureFlightQuality: () => ({ data: { quality: {} } }),
  useAgricultureFlightCoverage: () => ({ data: { coverage: {} } }),
  useAgricultureAnalysisRuns: () => ({ data: [{ id: "run-1", status: "completed", progress: 100, error: null }] }),
  useAgricultureAnalysisReadiness: () => ({ data: null, isLoading: false, isError: false }),
  useAgricultureAnalysisQuality: () => ({ data: { stages: [] } }),
  useAgricultureRuntimeEvents: () => ({ data: { events: [], gap_detected: false } }),
  useCreateAgricultureAnalysisRun: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
  useProcessAgricultureAnalysisRun: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
}));
vi.mock("../../mission-runtime/hooks/useMissionRuntime", () => ({
  useMissionRuntime: () => ({
    connection: "online",
    telemetry: null,
    missionStatus: null,
    droneConnected: false,
    reconnect: vi.fn(),
  }),
}));
vi.mock("../hooks/useBrowserOnline", () => ({ useBrowserOnline: () => true }));
vi.mock("./AgricultureLiveControls", () => ({ AgricultureLiveControls: () => <div>Capture controls</div> }));
vi.mock("./AgricultureLiveMap", () => ({ AgricultureLiveMap: () => <div>Live map</div> }));
vi.mock("./FlightQualityPanel", () => ({ FlightQualityPanel: () => <div>Capture quality</div> }));
vi.mock("./AgricultureMediaInventoryPanel", () => ({ AgricultureMediaInventoryPanel: () => <div>Media inventory</div> }));
vi.mock("./AgricultureUploadPanel", () => ({ AgricultureUploadPanel: () => <div>Media upload</div> }));
vi.mock("./AnalysisRunProgress", () => ({ AnalysisRunProgress: () => <div>Analysis progress</div> }));
vi.mock("../../mission-runtime/components/MissionCommandPanel", () => ({ MissionCommandPanel: () => <div>Mission commands</div> }));

describe("AgricultureLiveStatusPanel", () => {
  it("keeps the flight surface focused on capture, quality, and analysis progress", () => {
    render(<MemoryRouter><AgricultureLiveStatusPanel flightId="flight-1" active={false} /></MemoryRouter>);
    expect(screen.getByText("Capture quality")).toBeInTheDocument();
    expect(screen.getByText("Analysis progress")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review findings" })).toHaveAttribute("href", "/dashboard/agriculture/analysis/run-1");
    expect(screen.queryByText(/Actions, prescriptions and exports/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Observation review/i)).not.toBeInTheDocument();
  });
});
