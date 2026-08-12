import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  AgricultureFieldProfile,
  AnalysisRunProgress,
  CoverageMapLayer,
  EvidenceFrameCarousel,
  ExportApprovalDialog,
  FlightQualityPanel,
  FlightTimeline,
  HealthLayerSwitcher,
  InspectionActionPanel,
  ObservationMap,
  ObservationReviewDrawer,
  SensorCalibrationPanel,
} from "../index";
import type { AgricultureFieldProfile as Profile, AgricultureSensorStatus } from "../types";
import { server } from "../../../test/msw/server";

const profile: Profile = {
  id: 1, field_id: 7, crop_type: "wheat", variety: null, season: "2026",
  planting_date: null, growth_stage: "tillering", row_direction_deg: null,
  expected_row_spacing_m: null, soil_type: null, irrigation_method: null,
  management_zone: null, timezone: "UTC", notes: null, metadata: {},
};
const sensorStatus: AgricultureSensorStatus = {
  flight_id: "flight-1", inventory: ["rgb"], spectral: { status: "not_required" },
  calibration_ids: [], readings: {}, status: "pass",
};
describe("agriculture component state matrix", () => {
  beforeEach(() => {
    server.use(
      http.get("*/agriculture/fields/:fieldId/boundary-context", () =>
        HttpResponse.json({
          field_id: 7,
          name: "Test",
          area_ha: 1,
          boundary: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
          current_revision: 1,
          revisions: [],
          zones: [],
        }),
      ),
      http.get("*/agriculture/fields/:fieldId/plans", () => HttpResponse.json([])),
      http.get("*/api/alerts*", () => HttpResponse.json({ items: [] })),
    );
  });

  it("covers empty, pending, blocked, error, review and approval states", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <>
        <AgricultureFieldProfile fieldId={7} value={profile} />
        <FlightQualityPanel quality={{ status: "blocked" }} coverage={{ status: "warning", telemetry_gap_count: 2 }} />
        <CoverageMapLayer geojson={{ features: [] }} />
        <ObservationMap geojson={{ features: [] }} />
        <HealthLayerSwitcher layer="all" onLayerChange={vi.fn()} confidence={0.5} onConfidenceChange={vi.fn()} severity={0.5} onSeverityChange={vi.fn()} />
        <FlightTimeline flights={[]} value={0} onChange={vi.fn()} />
        <AnalysisRunProgress status="failed" progress={0.4} error="Worker failed" />
        <SensorCalibrationPanel status={sensorStatus} />
        <InspectionActionPanel actions={[]} loading={false} onGenerate={vi.fn()} onReview={vi.fn()} onAssign={vi.fn()} />
        <ExportApprovalDialog exports={[]} pending={false} error onGenerate={vi.fn()} onDownload={vi.fn()} />
          </>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Quality gate blocked/i)).toBeVisible();
    expect(screen.getAllByText(/No georeferenced features/i)).toHaveLength(2);
    expect(screen.getByText(/Worker failed/i)).toBeVisible();
    expect(screen.getByText(/No inspection actions/i)).toBeVisible();
    expect(screen.getByText(/Export blocked/i)).toBeVisible();
  });

  it("covers review and evidence empty states with a query boundary", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ObservationReviewDrawer observation={null} />
        <EvidenceFrameCarousel observationId={null} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Select an observation/i)).toBeVisible();
  });
});
