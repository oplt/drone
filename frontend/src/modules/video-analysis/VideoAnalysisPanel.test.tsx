import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VideoAnalysisPanel } from "./VideoAnalysisPanel";

vi.mock("./hooks", () => ({
  useMissionVideos: () => ({ data: [], refetch: vi.fn(), isLoading: false }),
  useUploadVideo: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
  useStartAnalysis: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
  useAnalysisJob: () => ({ data: null }),
  useDetections: () => ({ data: { items: [] }, isLoading: false }),
  useDetectionAggregates: () => ({ data: { buckets: [] } }),
  useDetectionWindow: () => ({ data: null }),
  useAnalysisSummary: () => ({ data: null }),
  useCancelAnalysis: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLiveSavedDetections: () => ({ data: [], isLoading: false }),
}));

vi.mock("./components/AnalysisWorkflowTabs", () => ({
  AnalysisWorkflowTabs: () => <div>Workflow tabs</div>,
  CollapsibleDetectionLogs: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));

vi.mock("./components/DetectionLogsTabs", () => ({
  DetectionLogsTabs: () => <div>Logs</div>,
}));

vi.mock("./components/DetectionMap", () => ({
  DetectionMap: () => <div>Map</div>,
}));

vi.mock("./components/DetectionTimeline", () => ({
  DetectionTimeline: () => <div>Timeline</div>,
}));

vi.mock("./components/VideoOverlayPlayer", () => ({
  VideoOverlayPlayer: () => <div>Player</div>,
}));

function forceTabletDownMd() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: /max-width:\s*899/.test(query) || query.includes("max-width:899"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

describe("VideoAnalysisPanel mobile tabs", () => {
  beforeEach(() => {
    forceTabletDownMd();
  });

  it("wires aria-controls ids for Player / Results / Map tabs", () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <VideoAnalysisPanel embedded />
      </ThemeProvider>,
    );

    const player = screen.getByRole("tab", { name: "Player" });
    const results = screen.getByRole("tab", { name: "Results" });
    const map = screen.getByRole("tab", { name: "Map / Logs" });

    expect(player).toHaveAttribute("id", "video-mobile-tab-player");
    expect(player).toHaveAttribute("aria-controls", "video-mobile-panel-player");
    expect(results).toHaveAttribute("aria-controls", "video-mobile-panel-results");
    expect(map).toHaveAttribute("aria-controls", "video-mobile-panel-map");
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "id",
      "video-mobile-panel-player",
    );
  });
});
