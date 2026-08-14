import { useMemo } from "react";
import {
  useAgricultureAnalysisRun,
  useAgricultureFieldContext,
  useAgricultureFlight,
  useAgricultureTelemetryTrack,
} from "../hooks";
import { AgricultureAnalysisMap } from "./AgricultureAnalysisMap";
import type {
  AgricultureMapContextStatus,
  AgricultureMapGeoJson,
} from "./AgricultureAnalysisMap";

const EMPTY_GEOJSON: AgricultureMapGeoJson = {
  type: "FeatureCollection",
  features: [],
};

function geometryFeatureCollection(
  geometry: Record<string, unknown> | null | undefined,
  properties: Record<string, unknown>,
): AgricultureMapGeoJson | null {
  if (!geometry?.type || !geometry.coordinates) return null;
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", geometry, properties }],
  };
}

export function AgricultureReviewMapPanel({
  runId,
  geojson,
  layerKind,
  selectedId,
  onSelect,
}: {
  runId: string;
  geojson: AgricultureMapGeoJson;
  layerKind: "observations" | "quality";
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const run = useAgricultureAnalysisRun(runId);
  const flightId = run.data?.flight_id ?? null;
  const flight = useAgricultureFlight(flightId);
  const field = useAgricultureFieldContext(flight.data?.field_id ?? null);
  const telemetry = useAgricultureTelemetryTrack(flightId);
  const fieldBoundary = useMemo(
    () =>
      geometryFeatureCollection(field.data?.boundary, {
        field_id: field.data?.field_id,
        kind: "field_boundary",
      }),
    [field.data?.boundary, field.data?.field_id],
  );
  const flightPath = useMemo(() => {
    const coordinates = (telemetry.data?.samples ?? []).map((sample) => [
      sample.lon,
      sample.lat,
    ]);
    return coordinates.length >= 2
      ? geometryFeatureCollection(
          { type: "LineString", coordinates },
          {
            flight_id: flightId,
            kind: "recorded_flight_path",
            sample_count: coordinates.length,
          },
        )
      : null;
  }, [flightId, telemetry.data?.samples]);
  const contextStatus: AgricultureMapContextStatus = {
    fieldBoundary:
      field.isLoading || flight.isLoading || run.isLoading
        ? "loading"
        : fieldBoundary
          ? "available"
          : "unavailable",
    flightPath:
      telemetry.isLoading || run.isLoading
        ? "loading"
        : telemetry.data?.truncated
          ? "partial"
          : flightPath
            ? "available"
            : "unavailable",
  };

  return (
    <AgricultureAnalysisMap
      observations={layerKind === "observations" ? geojson : EMPTY_GEOJSON}
      severityAreas={layerKind === "quality" ? geojson : null}
      fieldBoundary={fieldBoundary}
      flightPath={flightPath}
      selectedId={selectedId}
      onSelect={onSelect}
      contextStatus={contextStatus}
      initialVisibility={{ heatmap: false }}
    />
  );
}
