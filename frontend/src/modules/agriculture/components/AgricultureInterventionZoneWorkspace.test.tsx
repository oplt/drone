import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgricultureInterventionZoneWorkspace } from "./AgricultureInterventionZoneWorkspace";

const createMutate = vi.hoisted(() => vi.fn());
const zoneQuery = vi.hoisted(() => vi.fn());

vi.mock("../hooks", () => ({
  useAgricultureObservationPage: () => ({
    data: {
      total: 1,
      items: [{ id: "obs-1", observation_type: "weed", review_state: "confirmed", area_m2: 12, geometry_geojson: { type: "Polygon", coordinates: [] } }],
    },
  }),
}));
vi.mock("../workflows/interventionZones", () => ({
  useAgricultureInterventionZones: zoneQuery,
  useCreateAgricultureInterventionZone: () => ({ mutate: createMutate, isPending: false, isError: false }),
}));
vi.mock("./AgricultureAnalysisMap", () => ({ AgricultureAnalysisMap: () => <div>zone GIS map</div> }));
vi.mock("./InterventionZoneEditorCard", () => ({ InterventionZoneEditorCard: () => <div>zone editor</div> }));

describe("AgricultureInterventionZoneWorkspace", () => {
  it("proposes a zone only from explicitly selected confirmed observations", async () => {
    zoneQuery.mockReturnValue({ data: [] });
    const user = userEvent.setup();
    render(<AgricultureInterventionZoneWorkspace runId="run-1" />);

    await user.click(screen.getByRole("checkbox", { name: /weed.*obs-1/i }));
    await user.type(screen.getByLabelText("Zone name"), "North weeds");
    await user.click(screen.getByRole("button", { name: "Propose zone" }));

    expect(createMutate).toHaveBeenCalledWith(
      { runId: "run-1", payload: { name: "North weeds", category: "scouting", source_observation_ids: ["obs-1"] } },
      expect.any(Object),
    );
  });

  it("renders persisted zone geometry on the GIS map", () => {
    zoneQuery.mockReturnValue({ data: [{ id: "zone-1", name: "North weeds", status: "approved", revision: 2, geometry_geojson: { type: "Polygon", coordinates: [] } }] });
    render(<AgricultureInterventionZoneWorkspace runId="run-1" />);
    expect(screen.getByText("zone GIS map")).toBeInTheDocument();
    expect(screen.getByText("zone editor")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /North weeds.*approved/i })).toBeInTheDocument();
  });
});
