import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { PrioritizedFindingsPanel } from "./PrioritizedFindingsPanel";

const selectDetectionEvidence = vi.fn();

vi.mock("../../video-analysis/evidenceSelection", () => ({
  selectDetectionEvidence: (...args: unknown[]) => selectDetectionEvidence(...args),
}));

vi.mock("../hooks", () => ({
  useAgricultureFindings: () => ({
    data: {
      policy_version: "finding_rank_v1",
      items: [
        {
          rank: 1,
          finding_id: "obs-1",
          observation_id: "obs-1",
          observation_type: "weed_detection",
          geometry_geojson: { type: "Point", coordinates: [1, 2] },
          severity: 0.8,
          confidence: 0.7,
          area_m2: 12,
          georef_status: "resolved",
          review_state: "unreviewed",
          evidence_ids: ["e1"],
          model_version: "m1",
          provenance: {},
          assigned_to_user_id: null,
          merged_into_id: null,
          member_observation_ids: [],
          score: 0.81,
          display_status: "shown",
          policy_version: "finding_rank_v1",
          factors: { severity: { contribution: 0.2 } },
          withhold_reasons: [],
          limitations: [],
        },
      ],
      hotspots: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: { type: "Point", coordinates: [1, 2] },
            properties: { observation_id: "obs-1", severity: 0.8 },
          },
        ],
      },
    },
    isLoading: false,
    isError: false,
  }),
  useReviewAgricultureObservation: () => ({ mutate: vi.fn(), isPending: false }),
  useMergeAgricultureFindings: () => ({ mutate: vi.fn(), isPending: false }),
  useSplitAgricultureFinding: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateAgricultureFieldOutcome: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("./ObservationReviewDrawer", () => ({
  ObservationReviewDrawer: ({
    focusEvidence,
  }: {
    focusEvidence?: boolean;
  }) => (
    <div>
      Review drawer {focusEvidence ? "evidence-focused" : "default"}
    </div>
  ),
}));

describe("PrioritizedFindingsPanel", () => {
  const renderPanel = (ui: React.ReactElement) =>
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>
      </MemoryRouter>,
    );

  it("renders ranked findings and hotspot preview", () => {
    renderPanel(<PrioritizedFindingsPanel runId="run-1" />);
    expect(screen.getByText(/Prioritized findings/i)).toBeInTheDocument();
    expect(screen.getByText(/weed detection/i)).toBeInTheDocument();
    expect(screen.getByText(/Score 0.810/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("hides hotspot preview when showHotspotMap is false", () => {
    renderPanel(<PrioritizedFindingsPanel runId="run-1" showHotspotMap={false} />);
    expect(screen.getByText(/Prioritized findings/i)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Agriculture analysis map layer/i })).not.toBeInTheDocument();
  });

  it("jumps to evidence in one action and syncs URL state", async () => {
    selectDetectionEvidence.mockClear();
    const user = userEvent.setup();
    renderPanel(<PrioritizedFindingsPanel runId="run-1" showHotspotMap={false} />);

    await user.click(
      screen.getByRole("button", { name: "Jump to evidence for finding 1" }),
    );

    expect(selectDetectionEvidence).toHaveBeenCalledWith("e1");
    expect(screen.getByText("Review drawer evidence-focused")).toBeInTheDocument();
    expect(screen.getByText(/Selected finding obs-1/i)).toBeInTheDocument();
  });
});
