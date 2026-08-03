import { useQuery } from "@tanstack/react-query";
import {
  approveAgricultureAssistantRun,
  approveAgricultureInspectionAction,
  assignAgricultureInspectionAction,
  approveAgriculturePrescription,
  cancelAgricultureAnalysisRun,
  compareAgricultureFlight,
  completeAgricultureUpload,
  correctAgricultureGrowthStage,
  createAgricultureAnalysisRun,
  createAgricultureAnnotation,
  createAgricultureExport,
  createAgricultureInspectionPlan,
  createAgriculturePrescription,
  getAgricultureAnalysisLayer,
  getAgricultureSpatialViewport,
  getAgricultureAnalysisQuality,
  getAgricultureAnalysisRun,
  getAgricultureExportDownload,
  getAgricultureFlight,
  getAgricultureFlightCoverage,
  getAgricultureFlightQuality,
  getAgricultureObservationEvidence,
  getAgricultureProfile,
  getAgricultureSensorStatus,
  getAgricultureGrowthStage,
  getAgricultureYieldForecast,
  initiateAgricultureUpload,
  listAgricultureAnalysisRuns,
  listAgricultureAssistantRuns,
  listAgricultureComparisons,
  listAgricultureCropRisks,
  listAgricultureExports,
  listAgricultureFieldFlights,
  listAgricultureFieldOverviews,
  listAgricultureSpatialLayers,
  listAgricultureFusionResults,
  listAgricultureGrowthMetrics,
  listAgricultureInspectionActions,
  listAgricultureObservations,
  listAgricultureObservationPage,
  listAgriculturePrescriptions,
  listAgricultureTimeline,
  patchAgricultureProfile,
  processAgricultureAnalysisRun,
  processAgricultureCropRisks,
  processAgricultureFusion,
  processAgricultureGrowthMetric,
  processAgricultureGrowthStage,
  processAgricultureYieldForecast,
  replayAgricultureAnalysisRun,
  retryAgricultureAnalysisStage,
  reviewAgricultureObservation,
  runAgricultureAssistant,
  uploadAgricultureChunk,
  createAgriculturePlan,
  updateAgriculturePlanGrid,
  evaluateAgriculturePreflight,
  acknowledgeAgriculturePreflight,
  getAgricultureMediaInventory,
  getAgricultureRuntimeEvents,
  sendAgricultureRuntimeCommand,
  getAgricultureMediaTimeline,
  getAgricultureTelemetryWindow,
  listAgricultureTimelineBookmarks,
  saveAgricultureTimelineBookmark,
  getAgricultureReport,
  createAgricultureReportSnapshot,
  listAgricultureReportSnapshots,
  reconcileAgricultureMedia,
  revokeAgricultureMedia,
  restoreAgricultureMedia,
  backupAgricultureMedia,
  listAgricultureModels,
  listAgricultureModelQualityReports,
  getAgricultureModelReleaseGate,
  runAgricultureModelShadowEvaluation,
  publishAgricultureModel,
  rollbackAgricultureModel,
  monitorAgricultureModelDrift,
  registerAgricultureSensorCalibration,
  listAgricultureObservationAudits,
  getAgricultureFieldContext,
  createAgricultureField,
  updateAgricultureBoundary,
  addAgricultureZone,
  deleteAgricultureZone,
  assignAgricultureObservation,
  listAgricultureObservationFeedback,
  submitAgricultureObservationFeedback,
  decideAgricultureObservationFeedback,
  createAgricultureObservationAlert,
} from "./api";
import { useMutation, useQueryClient } from "@tanstack/react-query";

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
  fieldFlights: (fieldId: number | null) =>
    [...agricultureKeys.all, "field-flights", fieldId] as const,
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
  spatial: (runId: string | null, layer: string, zoom: number, minConfidence: number) => [...agricultureKeys.all, "spatial", runId, layer, zoom, minConfidence] as const,
  fieldContext: (fieldId: number | null) => [...agricultureKeys.all, "field-context", fieldId] as const,
};

export function useRevokeAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ mediaId, reason }: { mediaId: string; reason: string }) => revokeAgricultureMedia(mediaId, reason), onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.all }); } });
}
export function useRestoreAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ mediaId, reason }: { mediaId: string; reason: string }) => restoreAgricultureMedia(mediaId, reason), onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.all }); } });
}
export function useBackupAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ mediaId, reason }: { mediaId: string; reason: string }) => backupAgricultureMedia(mediaId, reason), onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.all }); } });
}

export function useAgricultureFieldContext(fieldId: number | null) {
  return useQuery({ queryKey: agricultureKeys.fieldContext(fieldId), queryFn: () => getAgricultureFieldContext(fieldId as number), enabled: fieldId != null });
}

export function useCreateAgricultureField() {
  const client = useQueryClient();
  return useMutation({ mutationFn: createAgricultureField, onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldCatalog() }); } });
}

export function useUpdateAgricultureBoundary() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ fieldId, boundary, reason }: { fieldId: number; boundary: Record<string, unknown>; reason?: string }) => updateAgricultureBoundary(fieldId, { boundary, reason }), onSuccess: (context) => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldContext(context.field_id) }); void client.invalidateQueries({ queryKey: agricultureKeys.fieldCatalog() }); } });
}

export function useAddAgricultureZone() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ fieldId, payload }: { fieldId: number; payload: Parameters<typeof addAgricultureZone>[1] }) => addAgricultureZone(fieldId, payload), onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldContext(variables.fieldId) }); } });
}

export function useDeleteAgricultureZone() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ fieldId, zoneId }: { fieldId: number; zoneId: string }) => deleteAgricultureZone(fieldId, zoneId), onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: agricultureKeys.fieldContext(variables.fieldId) }); } });
}

export function useCreateAgriculturePlan() {
  return useMutation({ mutationFn: createAgriculturePlan });
}

export function useUpdateAgriculturePlanGrid() {
  return useMutation({ mutationFn: ({ planId, expectedRevision, routeLonlat }: { planId: string; expectedRevision: number; routeLonlat: number[][] }) => updateAgriculturePlanGrid(planId, { expected_revision: expectedRevision, route_lonlat: routeLonlat }) });
}

export function useEvaluateAgriculturePreflight() {
  return useMutation({ mutationFn: ({ planId, notes }: { planId: string; notes?: string }) => evaluateAgriculturePreflight(planId, { notes }) });
}

export function useAcknowledgeAgriculturePreflight() {
  return useMutation({ mutationFn: acknowledgeAgriculturePreflight });
}

export function useAgricultureMediaInventory(flightId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.mediaInventory(flightId),
    queryFn: () => getAgricultureMediaInventory(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: 5000,
  });
}

export function useReconcileAgricultureMedia() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: reconcileAgricultureMedia,
    onSuccess: (inventory) => {
      void client.setQueryData(agricultureKeys.mediaInventory(inventory.flight_id), inventory);
    },
  });
}

export function useAgricultureMediaTimeline(flightId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.mediaTimeline(flightId),
    queryFn: () => getAgricultureMediaTimeline(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 15_000,
  });
}

export function useAgricultureTelemetryWindow(flightId: string | null, timestampUtc: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.mediaTimeline(flightId), "telemetry-window", timestampUtc],
    queryFn: () => getAgricultureTelemetryWindow(flightId as string, timestampUtc),
    enabled: Boolean(flightId && timestampUtc),
    staleTime: 10_000,
  });
}

export function useAgricultureTimelineBookmarks(flightId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.mediaTimeline(flightId), "bookmarks"], queryFn: () => listAgricultureTimelineBookmarks(flightId as string), enabled: Boolean(flightId) });
}
export function useSaveAgricultureTimelineBookmark() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ flightId, frameLineageId, note }: { flightId: string; frameLineageId: string; note?: string }) => saveAgricultureTimelineBookmark(flightId, { frame_lineage_id: frameLineageId, note }), onSuccess: (bookmark) => { void client.invalidateQueries({ queryKey: [...agricultureKeys.mediaTimeline(bookmark.flight_id ?? null), "bookmarks"] }); } });
}

export function useAgricultureReport(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.report(runId),
    queryFn: () => getAgricultureReport(runId as string),
    enabled: Boolean(runId),
    staleTime: 15_000,
  });
}

export function useAgricultureReportSnapshots(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.reportSnapshots(runId),
    queryFn: () => listAgricultureReportSnapshots(runId as string),
    enabled: Boolean(runId),
  });
}

export function useCreateAgricultureReportSnapshot() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, templateKey }: { runId: string; templateKey?: "standard" | "executive" | "field_visit" }) => createAgricultureReportSnapshot(runId, templateKey),
    onSuccess: (_snapshot, variables) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.reportSnapshots(variables.runId) });
    },
  });
}

export function useAgricultureRuntimeEvents(
  flightId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: agricultureKeys.runtimeEvents(flightId),
    queryFn: () => getAgricultureRuntimeEvents(flightId as string),
    enabled: Boolean(flightId) && enabled,
    refetchInterval: 3000,
  });
}

export function useAgricultureRuntimeCommand() {
  return useMutation({ mutationFn: ({ flightId, command, reason, expectedSequence }: { flightId: string; command: "pause" | "resume" | "abort" | "rth" | "land"; reason?: string; expectedSequence?: number }) => sendAgricultureRuntimeCommand(flightId, { command_id: `${flightId}-${command}-${crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`}`.slice(0, 120), command, reason, expected_sequence: expectedSequence }) });
}

export function useAgricultureObservationAudits(observationId: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "observation-audit", observationId],
    queryFn: () => listAgricultureObservationAudits(observationId as string),
    enabled: Boolean(observationId),
  });
}
export function useAgricultureObservationFeedback(observationId: string | null) {
  return useQuery({ queryKey: agricultureKeys.feedback(observationId), queryFn: () => listAgricultureObservationFeedback(observationId as string), enabled: Boolean(observationId) });
}
export function useAssignAgricultureObservation() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof assignAgricultureObservation>[1] }) => assignAgricultureObservation(id, payload), onSuccess: (observation) => { void client.invalidateQueries({ queryKey: agricultureKeys.observations(observation.run_id) }); } });
}
export function useSubmitAgricultureObservationFeedback() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof submitAgricultureObservationFeedback>[1] }) => submitAgricultureObservationFeedback(id, payload), onSuccess: (feedback) => { void client.invalidateQueries({ queryKey: agricultureKeys.feedback(feedback.observation_id) }); } });
}
export function useDecideAgricultureObservationFeedback() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof decideAgricultureObservationFeedback>[1] }) => decideAgricultureObservationFeedback(id, payload), onSuccess: (feedback) => { void client.invalidateQueries({ queryKey: agricultureKeys.feedback(feedback.observation_id) }); void client.invalidateQueries({ queryKey: agricultureKeys.observations(null) }); } });
}
export function useCreateAgricultureObservationAlert() {
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof createAgricultureObservationAlert>[1] }) => createAgricultureObservationAlert(id, payload) });
}

export function useAgricultureProfile(fieldId: number | null) {
  return useQuery({
    queryKey: agricultureKeys.profile(fieldId),
    queryFn: () => getAgricultureProfile(fieldId as number),
    enabled: fieldId != null,
  });
}
export function usePatchAgricultureProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      fieldId,
      payload,
    }: {
      fieldId: number;
      payload: Partial<import("./types").AgricultureFieldProfile>;
    }) => patchAgricultureProfile(fieldId, payload),
    onSuccess: (profile) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.profile(profile.field_id),
      });
    },
  });
}

export function useAgricultureAnalysisQuality(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.qualityRun(runId),
    queryFn: () => getAgricultureAnalysisQuality(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      [
        "pass",
        "warning",
        "blocked",
        "completed",
        "review",
        "failed",
        "blocked_quality",
      ].includes(query.state.data?.status ?? "")
        ? false
        : 3000,
  });
}
export function useAgricultureAnalysisRun(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.analysisRun(runId),
    queryFn: () => getAgricultureAnalysisRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      ["completed", "failed", "blocked", "review"].includes(
        query.state.data?.status ?? "",
      )
        ? false
        : 3000,
  });
}
export function useAgricultureFieldFlights(fieldId: number | null) {
  return useQuery({
    queryKey: agricultureKeys.fieldFlights(fieldId),
    queryFn: () => listAgricultureFieldFlights(fieldId as number),
    enabled: fieldId != null,
    staleTime: 10_000,
  });
}
export function useAgricultureFields() {
  return useQuery({
    queryKey: agricultureKeys.fieldCatalog(),
    queryFn: listAgricultureFieldOverviews,
    staleTime: 10_000,
  });
}
export function useAgricultureObservations(
  runId: string | null,
  minConfidence = 0,
) {
  return useQuery({
    queryKey: [...agricultureKeys.observations(runId), minConfidence],
    queryFn: () =>
      listAgricultureObservations(runId as string, { minConfidence }),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}

export function useAgricultureObservationPage(
  runId: string | null,
  filters: { minConfidence?: number; cursor?: string; limit?: number } = {},
) {
  return useQuery({
    queryKey: [
      ...agricultureKeys.observations(runId),
      "page",
      filters.minConfidence ?? 0,
      filters.cursor ?? null,
      filters.limit ?? 500,
    ],
    queryFn: () => listAgricultureObservationPage(runId as string, filters),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureObservationEvidence(
  observationId: string | null,
) {
  return useQuery({
    queryKey: agricultureKeys.evidence(observationId),
    queryFn: () => getAgricultureObservationEvidence(observationId as string),
    enabled: Boolean(observationId),
    staleTime: 30_000,
  });
}
export function useAgricultureSensorStatus(
  flightId: string | null,
  active = false,
) {
  return useQuery({
    queryKey: agricultureKeys.sensors(flightId),
    queryFn: () => getAgricultureSensorStatus(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: active ? 5000 : false,
    staleTime: 5000,
  });
}
export function useAgricultureModels(task?: string) {
  return useQuery({ queryKey: agricultureKeys.models(task), queryFn: () => listAgricultureModels(task), staleTime: 30_000 });
}
export function useAgricultureModelQualityReports(modelId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.models(), "quality", modelId], queryFn: () => listAgricultureModelQualityReports(modelId as string), enabled: Boolean(modelId), staleTime: 30_000 });
}
export function useAgricultureModelReleaseGate(modelId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.models(), "release-gate", modelId], queryFn: () => getAgricultureModelReleaseGate(modelId as string), enabled: Boolean(modelId), staleTime: 10_000 });
}
export function useAgricultureModelGovernanceActions() {
  const client = useQueryClient();
  const invalidate = () => { void client.invalidateQueries({ queryKey: agricultureKeys.models() }); };
  return {
    shadow: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof runAgricultureModelShadowEvaluation>[1] }) => runAgricultureModelShadowEvaluation(id, payload), onSuccess: invalidate }),
    publish: useMutation({ mutationFn: publishAgricultureModel, onSuccess: invalidate }),
    rollback: useMutation({ mutationFn: ({ id, targetId }: { id: string; targetId: string }) => rollbackAgricultureModel(id, targetId), onSuccess: invalidate }),
    drift: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof monitorAgricultureModelDrift>[1] }) => monitorAgricultureModelDrift(id, payload), onSuccess: invalidate }),
  };
}
export function useRegisterAgricultureSensorCalibration() {
  const client = useQueryClient();
  return useMutation({ mutationFn: registerAgricultureSensorCalibration, onSuccess: () => { void client.invalidateQueries({ queryKey: agricultureKeys.sensors(null) }); } });
}
export function useAgricultureFusionResults(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.fusion(runId),
    queryFn: () => listAgricultureFusionResults(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureCropRisks(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.cropRisks(runId),
    queryFn: () => listAgricultureCropRisks(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureGrowthMetrics(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.growth(runId),
    queryFn: () => listAgricultureGrowthMetrics(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureGrowthStage(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.stage(runId),
    queryFn: () => getAgricultureGrowthStage(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureYieldForecast(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.yield(runId),
    queryFn: () => getAgricultureYieldForecast(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureInspectionActions(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.actions(runId),
    queryFn: () => listAgricultureInspectionActions(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgriculturePrescriptions(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.prescriptions(runId),
    queryFn: () => listAgriculturePrescriptions(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureExports(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.exports(runId),
    queryFn: () => listAgricultureExports(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useAgricultureAssistantRuns(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.assistant(runId),
    queryFn: () => listAgricultureAssistantRuns(runId as string),
    enabled: Boolean(runId),
    refetchInterval: 5000,
  });
}
export function useRunAgricultureAssistant() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: { task: string; question: string };
    }) => runAgricultureAssistant(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.assistant(variables.runId),
      });
    },
  });
}
export function useApproveAgricultureAssistantRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
      note,
    }: {
      id: string;
      runId: string;
      status: "approved" | "rejected";
      note?: string;
    }) => approveAgricultureAssistantRun(id, status, note),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.assistant(variables.runId),
      });
    },
  });
}
export function useAgricultureLayer(
  runId: string | null,
  layer: string | null,
) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "layer", runId, layer],
    queryFn: () =>
      getAgricultureAnalysisLayer(runId as string, layer as string),
    enabled: Boolean(runId && layer),
    staleTime: 15_000,
  });
}
export function useAgricultureSpatialViewport(runId: string | null, options: { layer?: string; zoom?: number; minSeverity?: number; minConfidence?: number } = {}) {
  const layer = options.layer ?? "all";
  const zoom = options.zoom ?? 12;
  const minConfidence = options.minConfidence ?? 0;
  return useQuery({
    queryKey: agricultureKeys.spatial(runId, layer, zoom, minConfidence),
    queryFn: () => getAgricultureSpatialViewport(runId as string, { ...options, layer, zoom, minConfidence }),
    enabled: Boolean(runId),
    staleTime: 15_000,
  });
}
export function useAgricultureSpatialLayers(runId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.all, "spatial-layers", runId], queryFn: () => listAgricultureSpatialLayers(runId as string), enabled: Boolean(runId), staleTime: 15_000 });
}
export function useCreateAgricultureAnalysisRun() {
  return useMutation({ mutationFn: createAgricultureAnalysisRun });
}
export function useInitiateAgricultureUpload() {
  return useMutation({
    mutationFn: ({
      flightId,
      payload,
    }: {
      flightId: string;
      payload: Parameters<typeof initiateAgricultureUpload>[1];
    }) => initiateAgricultureUpload(flightId, payload),
  });
}
export function useUploadAgricultureChunk() {
  return useMutation({
    mutationFn: ({
      session,
      chunk,
      signal,
    }: {
      session: Parameters<typeof uploadAgricultureChunk>[0];
      chunk: Blob;
      signal?: AbortSignal;
    }) => uploadAgricultureChunk(session, chunk, signal),
  });
}
export function useCompleteAgricultureUpload() {
  return useMutation({
    mutationFn: ({
      flightId,
      uploadId,
    }: {
      flightId: string;
      uploadId: string;
    }) => completeAgricultureUpload(flightId, uploadId),
  });
}
export function useAgricultureAnalysisRuns(flightId: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.flight(flightId), "analysis-runs"],
    queryFn: () => listAgricultureAnalysisRuns(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 5000,
  });
}
export function useProcessAgricultureAnalysisRun() {
  return useMutation({ mutationFn: processAgricultureAnalysisRun });
}
export function useCancelAgricultureAnalysisRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: cancelAgricultureAnalysisRun,
    onSuccess: (run) => {
      void client.invalidateQueries({
        queryKey: [...agricultureKeys.flight(run.flight_id), "analysis-runs"],
      });
      void client.invalidateQueries({
        queryKey: agricultureKeys.analysisRun(run.id),
      });
    },
  });
}
export function useReplayAgricultureAnalysisRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: replayAgricultureAnalysisRun,
    onSuccess: (run) => {
      void client.invalidateQueries({
        queryKey: [...agricultureKeys.flight(run.flight_id), "analysis-runs"],
      });
      void client.invalidateQueries({
        queryKey: agricultureKeys.analysisRun(run.id),
      });
    },
  });
}

export function useRetryAgricultureAnalysisStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, stageName, reason }: { runId: string; stageName: string; reason?: string }) => retryAgricultureAnalysisStage(runId, stageName, reason),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.qualityRun(result.run_id) });
      void client.invalidateQueries({ queryKey: agricultureKeys.analysisRun(result.run_id) });
    },
  });
}
export function useProcessAgricultureFusion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureFusion(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.fusion(variables.runId),
      });
    },
  });
}
export function useProcessAgricultureCropRisks() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureCropRisks(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.cropRisks(variables.runId),
      });
    },
  });
}
export function useProcessAgricultureGrowthMetric() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: Record<string, unknown>;
    }) => processAgricultureGrowthMetric(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.growth(variables.runId),
      });
    },
  });
}
export function useProcessAgricultureGrowthStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureGrowthStage(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.stage(variables.runId),
      });
    },
  });
}
export function useCorrectAgricultureGrowthStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      estimateId,
      payload,
    }: {
      estimateId: string;
      payload: { human_stage: string; note?: string };
    }) => correctAgricultureGrowthStage(estimateId, payload),
    onSuccess: (result) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.stage(result.run_id),
      });
    },
  });
}
export function useCreateAgricultureInspectionPlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => createAgricultureInspectionPlan(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.actions(variables.runId),
      });
    },
  });
}
export function useApproveAgricultureInspectionAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      runId: string;
      status: "approved" | "rejected";
    }) => approveAgricultureInspectionAction(id, status),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.actions(variables.runId),
      });
    },
  });
}
export function useAssignAgricultureInspectionAction() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (variables: { id: string; runId: string; payload: Parameters<typeof assignAgricultureInspectionAction>[1] }) => assignAgricultureInspectionAction(variables.id, variables.payload), onSuccess: (_result, variables) => { void client.invalidateQueries({ queryKey: agricultureKeys.actions(variables.runId) }); } });
}
export function useCreateAgriculturePrescription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, ruleId }: { runId: string; ruleId: string }) =>
      createAgriculturePrescription(runId, ruleId),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.prescriptions(variables.runId),
      });
    },
  });
}
export function useApproveAgriculturePrescription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      runId: string;
      status: "approved" | "rejected";
    }) => approveAgriculturePrescription(id, status),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.prescriptions(variables.runId),
      });
    },
  });
}
export function useCreateAgricultureExport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: { artifact_kind: string; format: string; source_id?: string };
    }) => createAgricultureExport(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.exports(variables.runId),
      });
    },
  });
}
export function useGetAgricultureExportDownload() {
  return useMutation({ mutationFn: getAgricultureExportDownload });
}
export function useProcessAgricultureYieldForecast() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureYieldForecast(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.yield(variables.runId),
      });
    },
  });
}
export function useReviewAgricultureObservation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: Parameters<typeof reviewAgricultureObservation>[1];
    }) => reviewAgricultureObservation(id, payload),
    onMutate: async ({ id, payload }) => {
      await client.cancelQueries({ queryKey: agricultureKeys.all });
      const snapshots = client.getQueriesData({
        queryKey: agricultureKeys.observations(null).slice(0, 2),
      });
      client.setQueriesData(
        { queryKey: agricultureKeys.all },
        (value: unknown) =>
          Array.isArray(value)
            ? value.map((row) =>
                (row as { id: string }).id === id
                  ? {
                      ...row,
                      review_state: payload.status,
                      review_label: payload.label ?? null,
                      review_note: payload.note ?? null,
                    }
                  : row,
              )
            : value,
      );
      return { snapshots };
    },
    onError: (_error, _variables, context) => {
      context?.snapshots.forEach(([key, value]) =>
        client.setQueryData(key, value),
      );
    },
    onSuccess: (updated) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.observations(updated.run_id),
      });
    },
  });
}
export function useAgricultureTimeline(fieldId: number | null) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "timeline", fieldId],
    queryFn: () => listAgricultureTimeline(fieldId as number),
    enabled: fieldId != null,
    staleTime: 30_000,
  });
}
export function useAgricultureComparisons(flightId: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "comparisons", flightId],
    queryFn: () => listAgricultureComparisons(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 10_000,
  });
}
export function useCompareAgricultureFlight() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      flightId,
      referenceFlightId,
    }: {
      flightId: string;
      referenceFlightId: string;
    }) =>
      compareAgricultureFlight(flightId, {
        reference_flight_id: referenceFlightId,
      }),
    onSuccess: (result) => {
      void client.invalidateQueries({
        queryKey: [
          ...agricultureKeys.all,
          "comparisons",
          result.current_flight_id,
        ],
      });
    },
  });
}
export function useCreateAgricultureAnnotation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      observationId,
      payload,
    }: {
      observationId: string;
      payload: Parameters<typeof createAgricultureAnnotation>[1];
    }) => createAgricultureAnnotation(observationId, payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: agricultureKeys.all });
    },
  });
}

export function useAgricultureFlight(flightId: string | null, active = false) {
  return useQuery({
    queryKey: agricultureKeys.flight(flightId),
    queryFn: () => getAgricultureFlight(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: active ? 3000 : false,
  });
}

export function useAgricultureFlightQuality(
  flightId: string | null,
  active = false,
) {
  return useQuery({
    queryKey: agricultureKeys.quality(flightId),
    queryFn: () => getAgricultureFlightQuality(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: active ? 3000 : false,
  });
}

export function useAgricultureFlightCoverage(
  flightId: string | null,
  active = false,
) {
  return useQuery({
    queryKey: agricultureKeys.coverage(flightId),
    queryFn: () => getAgricultureFlightCoverage(flightId as string),
    enabled: Boolean(flightId),
    refetchInterval: active ? 3000 : false,
  });
}
