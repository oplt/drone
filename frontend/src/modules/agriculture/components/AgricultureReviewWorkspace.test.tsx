import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AgricultureReviewWorkspace } from "./AgricultureReviewWorkspace";

const reviewMutate = vi.fn();

vi.mock("../hooks", () => ({
  useAgricultureAnalysisQuality: () => ({
    data: { status: "ok", score: 0.91, summary: { reasons: "ok" } },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useAgricultureLayer: () => ({ data: null, isError: false }),
  useAgricultureObservationPage: () => ({
    data: {
      items: [
        {
          id: "obs-1",
          observation_type: "weed",
          severity: 0.8,
          confidence: 0.9,
          area_m2: 4.2,
          geometry_geojson: { type: "Point", coordinates: [1, 2] },
          review_state: "unreviewed",
          evidence_ids: ["ev-1"],
          model_version: "m1",
          uncertainty: {},
        },
        {
          id: "obs-2",
          observation_type: "standing_water",
          severity: 0.1,
          confidence: 0.5,
          area_m2: 1,
          geometry_geojson: { type: "Point", coordinates: [2, 3] },
          review_state: "unreviewed",
          evidence_ids: [],
          model_version: "m1",
          uncertainty: {},
        },
      ],
      total: 2,
      next_cursor: null,
    },
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useAgricultureSpatialViewport: () => ({ data: null }),
  useAgricultureSpatialLayers: () => ({ data: { layers: [] } }),
  useReviewAgricultureObservation: () => ({
    mutate: reviewMutate,
    isPending: false,
  }),
  useAssignAgricultureObservation: () => ({ mutate: vi.fn(), isPending: false }),
  useAgricultureObservationFeedback: () => ({ data: [] }),
  useSubmitAgricultureObservationFeedback: () => ({
    mutate: vi.fn(),
    isPending: false,
    isSuccess: false,
  }),
  useDecideAgricultureObservationFeedback: () => ({ mutate: vi.fn() }),
  useCreateAgricultureObservationAlert: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useAgricultureObservationAudits: () => ({ data: [] }),
}));

vi.mock("./ObservationMap", () => ({
  ObservationMap: () => <div>Observation map</div>,
}));
vi.mock("./CoverageMapLayer", () => ({ CoverageMapLayer: () => null }));
vi.mock("./RGBProductPanel", () => ({ RGBProductPanel: () => null }));
vi.mock("./EvidenceFrameCarousel", () => ({
  EvidenceFrameCarousel: () => <div>Evidence</div>,
}));
vi.mock("./AssignReviewerDialog", () => ({
  AssignReviewerDialog: () => null,
}));
vi.mock("../../video-analysis/evidenceSelection", () => ({
  selectDetectionEvidence: vi.fn(),
}));

describe("AgricultureReviewWorkspace", () => {
  it("filters by layer, opens selection, and mutates review confirm", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter initialEntries={["/?layer=all"]}>
          <AgricultureReviewWorkspace runId="run-1" />
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByLabelText("Observation review list")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review weed/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Review standing water/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByLabelText("Health layer"));
    await user.click(await screen.findByRole("option", { name: "weed" }));
    expect(
      screen.queryByRole("button", { name: /Review standing water/i }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Review weed/i }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(reviewMutate).toHaveBeenCalled();
  });
});
