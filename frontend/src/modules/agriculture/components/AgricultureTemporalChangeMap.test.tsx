import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgricultureTemporalChangeMap } from "./AgricultureTemporalChangeMap";

const capture = vi.hoisted(() => vi.fn());
vi.mock("./AgricultureAnalysisMap", () => ({
  AgricultureAnalysisMap: (props: unknown) => { capture(props); return <div>temporal GIS map</div>; },
}));

describe("AgricultureTemporalChangeMap", () => {
  it("maps new, persistent and resolved states with count and area summary", () => {
    const base = {
      field_id: 1, current_flight_id: "f2", reference_flight_id: "f1",
      current_observation_id: "o2", previous_observation_id: "o1",
      observation_type: "weed", area_m2: 10, delta_intensity: 0,
      confidence: 0.8, evidence_ids: [], uncertainty: {}, created_at: "2026-01-01",
    };
    render(<AgricultureTemporalChangeMap changes={[
      { ...base, id: "new", state: "new", geometry_geojson: { type: "Polygon", coordinates: [] }, reference_geometry_geojson: {}, delta_area_m2: 4 },
      { ...base, id: "stable", state: "stable", geometry_geojson: { type: "Polygon", coordinates: [] }, reference_geometry_geojson: {}, delta_area_m2: 1 },
      { ...base, id: "resolved", state: "resolved", geometry_geojson: {}, reference_geometry_geojson: { type: "Polygon", coordinates: [] }, delta_area_m2: -2 },
    ]} onSelect={vi.fn()} />);

    expect(screen.getByText("temporal GIS map")).toBeInTheDocument();
    expect(screen.getByText("New 1")).toBeInTheDocument();
    expect(screen.getByText("Persistent 1")).toBeInTheDocument();
    expect(screen.getByText("Resolved 1")).toBeInTheDocument();
    expect(screen.getByText("Net area +3.0 m²")).toBeInTheDocument();
    const props = capture.mock.calls.at(-1)?.[0];
    expect(props.temporalChanges.features.map((feature: { properties: { lifecycle: string } }) => feature.properties.lifecycle)).toEqual(["new", "persistent", "resolved"]);
  });
});
