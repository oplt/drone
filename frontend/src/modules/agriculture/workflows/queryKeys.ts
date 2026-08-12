export const agricultureKeys = {
  all: ["agriculture"] as const,
  profile: (fieldId: number | null) =>
    [...agricultureKeys.all, "profile", fieldId] as const,
  flight: (flightId: string | null) =>
    [...agricultureKeys.all, "flight", flightId] as const,
  quality: (flightId: string | null) =>
    [...agricultureKeys.all, "quality", flightId] as const,
  coverage: (flightId: string | null) =>
    [...agricultureKeys.all, "coverage", flightId] as const,
  qualityRun: (runId: string | null) =>
    [...agricultureKeys.all, "quality-run", runId] as const,
  analysisRun: (runId: string | null) =>
    [...agricultureKeys.all, "analysis-run", runId] as const,
  analysisReadiness: (flightId: string | null) =>
    [...agricultureKeys.all, "analysis-readiness", flightId] as const,
  fieldFlights: (fieldId: number | null) =>
    [...agricultureKeys.all, "field-flights", fieldId] as const,
  fieldPlans: (fieldId: number | null) =>
    [...agricultureKeys.all, "field-plans", fieldId] as const,
  fieldCatalog: () => [...agricultureKeys.all, "field-catalog"] as const,
  observations: (runId: string | null) =>
    [...agricultureKeys.all, "observations", runId] as const,
  evidence: (observationId: string | null) =>
    [...agricultureKeys.all, "evidence", observationId] as const,
  feedback: (observationId: string | null) => [...agricultureKeys.all, "feedback", observationId] as const,
  sensors: (flightId: string | null) =>
    [...agricultureKeys.all, "sensors", flightId] as const,
  fusion: (runId: string | null) =>
    [...agricultureKeys.all, "fusion", runId] as const,
  cropRisks: (runId: string | null) =>
    [...agricultureKeys.all, "crop-risks", runId] as const,
  growth: (runId: string | null) =>
    [...agricultureKeys.all, "growth", runId] as const,
  stage: (runId: string | null) =>
    [...agricultureKeys.all, "stage", runId] as const,
  yield: (runId: string | null) =>
    [...agricultureKeys.all, "yield", runId] as const,
  actions: (runId: string | null) =>
    [...agricultureKeys.all, "actions", runId] as const,
  prescriptions: (runId: string | null) =>
  [...agricultureKeys.all, "prescriptions", runId] as const,
  models: (task?: string) => [...agricultureKeys.all, "models", task ?? "all"] as const,
  exports: (runId: string | null) =>
    [...agricultureKeys.all, "exports", runId] as const,
  assistant: (runId: string | null) =>
    [...agricultureKeys.all, "assistant", runId] as const,
  mediaInventory: (flightId: string | null) =>
    [...agricultureKeys.all, "media-inventory", flightId] as const,
  runtimeEvents: (flightId: string | null) =>
    [...agricultureKeys.all, "runtime-events", flightId] as const,
  mediaTimeline: (flightId: string | null) =>
    [...agricultureKeys.all, "media-timeline", flightId] as const,
  report: (runId: string | null) =>
    [...agricultureKeys.all, "report", runId] as const,
  reportSnapshots: (runId: string | null) =>
    [...agricultureKeys.all, "report-snapshots", runId] as const,
  findings: (runId: string | null) =>
    [...agricultureKeys.all, "findings", runId] as const,
  fieldOutcomes: (runId: string | null) =>
    [...agricultureKeys.all, "field-outcomes", runId] as const,
  comparableFlights: (flightId: string | null) =>
    [...agricultureKeys.all, "comparable-flights", flightId] as const,
  spatial: (runId: string | null, layer: string, zoom: number, minConfidence: number) => [...agricultureKeys.all, "spatial", runId, layer, zoom, minConfidence] as const,
  fieldContext: (fieldId: number | null) => [...agricultureKeys.all, "field-context", fieldId] as const,
};

export const agricultureInvalidationKeys = {
  mediaInventories: () => agricultureKeys.mediaInventory(null).slice(0, 2),
  observations: () => agricultureKeys.observations(null).slice(0, 2),
} as const;

export function agriculturePollInterval(
  intervalMs: number,
  active = true,
): number | false {
  const visible =
    typeof document === "undefined" || document.visibilityState === "visible";
  return active && visible ? intervalMs : false;
}
