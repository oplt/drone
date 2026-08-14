import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgricultureReviewMapPanel } from "./AgricultureReviewMapPanel";

const captureMapProps = vi.hoisted(() => vi.fn());

vi.mock("../hooks", () => ({
  useAgricultureAnalysisRun: () => ({
    data: { flight_id: "flight-1" },
    isLoading: false,
  }),
  useAgricultureFlight: () => ({
    data: { field_id: 7 },
    isLoading: false,
  }),
  useAgricultureFieldContext: () => ({
    data: {
      field_id: 7,
      boundary: {
        type: "Polygon",
        coordinates: [[[4, 50], [4.1, 50], [4, 50.1], [4, 50]]],
      },
    },
    isLoading: false,
  }),
  useAgricultureTelemetryTrack: () => ({
    data: {
      truncated: false,
      samples: [
        { lon: 4.01, lat: 50.01 },
        { lon: 4.02, lat: 50.02 },
      ],
    },
    isLoading: false,
  }),
}));

vi.mock("./AgricultureAnalysisMap", () => ({
  AgricultureAnalysisMap: (props: unknown) => {
    captureMapProps(props);
    return <div>GIS analysis map</div>;
  },
}));

describe("AgricultureReviewMapPanel", () => {
  beforeEach(() => captureMapProps.mockClear());

  it("builds overlays only from field and recorded telemetry sources", () => {
    render(
      <AgricultureReviewMapPanel
        runId="run-1"
        layerKind="observations"
        geojson={{ features: [] }}
      />,
    );
    expect(screen.getByText("GIS analysis map")).toBeInTheDocument();
    const props = captureMapProps.mock.calls.at(-1)?.[0];
    expect(props.fieldBoundary.features[0].geometry.coordinates).toEqual([
      [[4, 50], [4.1, 50], [4, 50.1], [4, 50]],
    ]);
    expect(props.flightPath.features[0].geometry).toEqual({
      type: "LineString",
      coordinates: [[4.01, 50.01], [4.02, 50.02]],
    });
    expect(props.contextStatus).toEqual({
      fieldBoundary: "available",
      flightPath: "available",
    });
  });
});
