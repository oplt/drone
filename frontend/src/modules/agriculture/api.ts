import { httpRequest } from "../../shared/api/httpClient";
import type {
  AgricultureFieldProfile,
  AgricultureFlight,
  AgricultureMissionProfile,
  AgriculturePlanPreview,
  AgricultureAnalysisRun,
  AgricultureAnalysisQuality,
  AgricultureObservation,
  AgricultureObservationPage,
  AgricultureLayer,
  AgricultureAnnotation,
  AgricultureChange,
  AgricultureComparison,
  AgricultureTimelineFlight,
  AgricultureSensorStatus,
  AgricultureFusionResult,
  AgricultureCropRisk,
  AgricultureGrowthMetric,
  AgricultureGrowthStage,
  AgricultureYieldForecast,
  AgricultureInspectionAction,
  AgriculturePrescription,
  AgricultureExport,
  AgricultureFieldOverview,
  AgricultureAssistantRun,
  AgricultureObservationEvidence,
  AgricultureUploadSession,
  AgriculturePlan,
  AgriculturePlanRequest,
  AgriculturePreflightSnapshot,
  AgricultureMediaInventory,
  AgricultureMediaTimeline,
  AgricultureTelemetryWindow,
  AgricultureTimelineBookmark,
  AgricultureReport,
  AgricultureReportSnapshot,
  AgricultureSensorCalibration,
  AgricultureModelVersion,
  AgricultureModelReleaseGate,
  AgricultureFieldContext,
  AgricultureFieldZone,
  AgricultureObservationFeedback,
  AgricultureSpatialViewport,
  AgricultureSpatialLayers,
  AgricultureMediaArtifact,
} from "./types";

export async function getAgricultureFieldContext(fieldId: number): Promise<AgricultureFieldContext> {
  return httpRequest<AgricultureFieldContext>(`/agriculture/fields/${fieldId}/boundary-context`);
}

export async function createAgricultureField(payload: { name: string; boundary: Record<string, unknown> }): Promise<AgricultureFieldContext> {
  return httpRequest<AgricultureFieldContext>("/agriculture/fields", { method: "POST", body: payload });
}

export async function updateAgricultureBoundary(fieldId: number, payload: { boundary: Record<string, unknown>; reason?: string }): Promise<AgricultureFieldContext> {
  return httpRequest<AgricultureFieldContext>(`/agriculture/fields/${fieldId}/boundary`, { method: "PUT", body: payload });
}

export async function addAgricultureZone(fieldId: number, payload: Omit<AgricultureFieldZone, "id" | "revision" | "created_at">): Promise<AgricultureFieldZone> {
  return httpRequest<AgricultureFieldZone>(`/agriculture/fields/${fieldId}/zones`, { method: "POST", body: payload });
}

export async function deleteAgricultureZone(fieldId: number, zoneId: string): Promise<void> {
  await httpRequest<void>(`/agriculture/fields/${fieldId}/zones/${encodeURIComponent(zoneId)}`, { method: "DELETE" });
}

export async function createAgriculturePlan(
  payload: AgriculturePlanRequest,
): Promise<AgriculturePlan> {
  return httpRequest<AgriculturePlan>("/agriculture/flights/plans", {
    method: "POST",
    body: payload,
  });
}

export async function validateAgriculturePlan(planId: string): Promise<AgriculturePlan> {
  return httpRequest<AgriculturePlan>(
    `/agriculture/flights/plans/${encodeURIComponent(planId)}/validate`,
    { method: "POST" },
  );
}

export async function updateAgriculturePlanGrid(planId: string, payload: { expected_revision: number; route_lonlat: number[][] }): Promise<AgriculturePlan> {
  return httpRequest<AgriculturePlan>(`/agriculture/flights/plans/${encodeURIComponent(planId)}/grid`, { method: "PUT", body: payload });
}

export async function evaluateAgriculturePreflight(
  planId: string,
  payload: { notes?: string },
): Promise<AgriculturePreflightSnapshot> {
  return httpRequest<AgriculturePreflightSnapshot>(
    `/agriculture/flights/plans/${encodeURIComponent(planId)}/preflight`,
    { method: "POST", body: payload },
  );
}

export async function acknowledgeAgriculturePreflight(
  snapshotId: string,
): Promise<AgriculturePreflightSnapshot> {
  return httpRequest<AgriculturePreflightSnapshot>(
    `/agriculture/preflight/${encodeURIComponent(snapshotId)}/acknowledge`,
    { method: "POST", body: { operator_confirmed: true } },
  );
}

export async function getAgricultureMediaInventory(
  flightId: string,
): Promise<AgricultureMediaInventory> {
  return httpRequest<AgricultureMediaInventory>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/media-inventory`,
  );
}

export async function getAgricultureMediaStatus(mediaId: string): Promise<AgricultureMediaArtifact & { flight_id: string; backup_available: boolean }> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/status`);
}
export async function revokeAgricultureMedia(mediaId: string, reason: string): Promise<unknown> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/revoke`, { method: "POST", body: { reason } });
}
export async function restoreAgricultureMedia(mediaId: string, reason: string): Promise<unknown> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/restore`, { method: "POST", body: { reason } });
}
export async function backupAgricultureMedia(mediaId: string, reason: string): Promise<unknown> {
  return httpRequest(`/agriculture/media/${encodeURIComponent(mediaId)}/backup`, { method: "POST", body: { reason } });
}

export async function getAgricultureMediaTimeline(flightId: string): Promise<AgricultureMediaTimeline> {
  return httpRequest<AgricultureMediaTimeline>(`/agriculture/flights/${encodeURIComponent(flightId)}/media-timeline`);
}

export async function getAgricultureTelemetryWindow(flightId: string, timestampUtc: string | null, windowSeconds = 15): Promise<AgricultureTelemetryWindow> {
  const params = new URLSearchParams({ window_seconds: String(windowSeconds) });
  if (timestampUtc) params.set("timestamp_utc", timestampUtc);
  return httpRequest<AgricultureTelemetryWindow>(`/agriculture/flights/${encodeURIComponent(flightId)}/telemetry-window?${params.toString()}`);
}

export async function listAgricultureTimelineBookmarks(flightId: string): Promise<{ flight_id: string; bookmarks: AgricultureTimelineBookmark[] }> {
  return httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/timeline/bookmarks`);
}
export async function saveAgricultureTimelineBookmark(flightId: string, payload: { frame_lineage_id: string; note?: string }): Promise<AgricultureTimelineBookmark> {
  return httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/timeline/bookmarks`, { method: "POST", body: payload });
}
export async function deleteAgricultureTimelineBookmark(flightId: string, bookmarkId: string): Promise<void> {
  await httpRequest(`/agriculture/flights/${encodeURIComponent(flightId)}/timeline/bookmarks/${encodeURIComponent(bookmarkId)}`, { method: "DELETE" });
}

export async function getAgricultureReport(runId: string): Promise<AgricultureReport> {
  return httpRequest<AgricultureReport>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/report`);
}

export async function createAgricultureReportSnapshot(runId: string, templateKey: "standard" | "executive" | "field_visit" = "standard"): Promise<AgricultureReportSnapshot> {
  return httpRequest<AgricultureReportSnapshot>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/report-snapshots`, { method: "POST", body: { template_key: templateKey } });
}

export async function listAgricultureReportSnapshots(runId: string): Promise<AgricultureReportSnapshot[]> {
  return httpRequest<AgricultureReportSnapshot[]>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/report-snapshots`);
}

export async function getAgricultureRuntimeEvents(
  flightId: string,
  afterSequence = 0,
): Promise<{ events: Array<Record<string, unknown>>; next_sequence: number; latest_sequence: number; has_more: boolean; gap_detected: boolean }> {
  return httpRequest<{ events: Array<Record<string, unknown>>; next_sequence: number; latest_sequence: number; has_more: boolean; gap_detected: boolean }>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/runtime/events?after_sequence=${afterSequence}`,
  );
}

export async function sendAgricultureRuntimeCommand(
  flightId: string,
  payload: { command_id: string; command: "pause" | "resume" | "abort" | "rth" | "land"; reason?: string; expected_sequence?: number },
) {
  return httpRequest<{ flight_id: string; command_id: string; command: string; accepted: boolean; state_before: string; state_after: string; message: string; sequence: number; duplicate: boolean }>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/runtime/commands`,
    { method: "POST", body: payload },
  );
}

export async function getAgricultureProfile(
  fieldId: number,
): Promise<AgricultureFieldProfile> {
  return httpRequest<AgricultureFieldProfile>(
    `/agriculture/fields/${fieldId}/profile`,
  );
}

export async function patchAgricultureProfile(
  fieldId: number,
  payload: Partial<AgricultureFieldProfile>,
): Promise<AgricultureFieldProfile> {
  return httpRequest<AgricultureFieldProfile>(
    `/agriculture/fields/${fieldId}/profile`,
    {
      method: "PATCH",
      body: payload,
    },
  );
}

export async function previewAgricultureFlight(payload: {
  field_id: number | null;
  field_polygon_lonlat: number[][];
  cruise_alt_m: number;
  route_length_m?: number | null;
  profile: AgricultureMissionProfile;
}): Promise<AgriculturePlanPreview> {
  return httpRequest<AgriculturePlanPreview>(
    "/agriculture/flights/plan-preview",
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function getAgricultureFlight(
  flightId: string,
): Promise<AgricultureFlight> {
  return httpRequest<AgricultureFlight>(
    `/agriculture/flights/${encodeURIComponent(flightId)}`,
  );
}

export async function getAgricultureFlightQuality(
  flightId: string,
): Promise<Record<string, unknown>> {
  return httpRequest<Record<string, unknown>>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/quality`,
  );
}

export async function getAgricultureFlightCoverage(
  flightId: string,
): Promise<Record<string, unknown>> {
  return httpRequest<Record<string, unknown>>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/coverage`,
  );
}

export async function getAgricultureSensorStatus(
  flightId: string,
): Promise<AgricultureSensorStatus> {
  return httpRequest<AgricultureSensorStatus>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/sensor-status`,
  );
}

export async function registerAgricultureSensorCalibration(payload: {
  id: string;
  sensor_serial: string;
  sensor_type: "multispectral" | "thermal" | "weather" | "humidity" | "soil_moisture" | "irrigation";
  version: string;
  calibration_kind: string;
  calibration_data?: Record<string, unknown>;
  checksum: string;
  valid_from?: string | null;
  valid_until?: string | null;
}): Promise<AgricultureSensorCalibration> {
  return httpRequest<AgricultureSensorCalibration>("/agriculture/sensor-calibrations", { method: "POST", body: payload });
}

export async function listAgricultureModels(task?: string): Promise<AgricultureModelVersion[]> {
  const query = task ? `?${new URLSearchParams({ task })}` : "";
  return httpRequest<AgricultureModelVersion[]>(`/agriculture/models${query}`);
}

export async function listAgricultureModelQualityReports(modelId: string): Promise<Array<Record<string, unknown>>> {
  return httpRequest<Array<Record<string, unknown>>>(`/agriculture/models/${encodeURIComponent(modelId)}/quality-reports`);
}
export async function getAgricultureModelReleaseGate(modelId: string, scope: { crop_type?: string; growth_stage?: string; sensor_type?: string } = {}): Promise<AgricultureModelReleaseGate> {
  const params = new URLSearchParams(Object.entries(scope).filter((entry): entry is [string, string] => Boolean(entry[1])));
  return httpRequest<AgricultureModelReleaseGate>(`/agriculture/models/${encodeURIComponent(modelId)}/release-gate?${params.toString()}`);
}
export async function runAgricultureModelShadowEvaluation(modelId: string, payload: { metrics: Record<string, number>; crop_type?: string; growth_stage?: string; sensor_type?: string; incumbent_metrics?: Record<string, number> }) {
  return httpRequest<Record<string, unknown>>(`/agriculture/models/${encodeURIComponent(modelId)}/shadow-evaluation`, { method: "POST", body: payload });
}
export async function publishAgricultureModel(modelId: string) {
  return httpRequest<Record<string, unknown>>(`/agriculture/models/${encodeURIComponent(modelId)}/publish`, { method: "POST" });
}
export async function rollbackAgricultureModel(modelId: string, targetModelId: string) {
  return httpRequest<Record<string, unknown>>(`/agriculture/models/${encodeURIComponent(modelId)}/rollback/${encodeURIComponent(targetModelId)}`, { method: "POST" });
}
export async function monitorAgricultureModelDrift(modelId: string, payload: { current: Record<string, number>; baseline: Record<string, number>; slices?: Record<string, Record<string, number>> }) {
  return httpRequest<Record<string, unknown>>(`/agriculture/models/${encodeURIComponent(modelId)}/drift-monitor`, { method: "POST", body: payload });
}
export async function processAgricultureFusion(
  runId: string,
  payload: Record<string, unknown> = {},
): Promise<AgricultureFusionResult[]> {
  return httpRequest<AgricultureFusionResult[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/fusion`,
    { method: "POST", body: payload },
  );
}
export async function listAgricultureFusionResults(
  runId: string,
): Promise<AgricultureFusionResult[]> {
  return httpRequest<AgricultureFusionResult[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/fusion-results`,
  );
}
export async function processAgricultureCropRisks(
  runId: string,
  payload: Record<string, unknown> = {},
): Promise<AgricultureCropRisk[]> {
  return httpRequest<AgricultureCropRisk[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/crop-risks`,
    { method: "POST", body: payload },
  );
}
export async function listAgricultureCropRisks(
  runId: string,
): Promise<AgricultureCropRisk[]> {
  return httpRequest<AgricultureCropRisk[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/crop-risks`,
  );
}
export async function processAgricultureGrowthMetric(
  runId: string,
  payload: Record<string, unknown>,
): Promise<AgricultureGrowthMetric> {
  return httpRequest<AgricultureGrowthMetric>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/growth-metrics`,
    { method: "POST", body: payload },
  );
}
export async function listAgricultureGrowthMetrics(
  runId: string,
): Promise<AgricultureGrowthMetric[]> {
  return httpRequest<AgricultureGrowthMetric[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/growth-metrics`,
  );
}
export async function processAgricultureGrowthStage(
  runId: string,
  payload: Record<string, unknown> = {},
): Promise<AgricultureGrowthStage> {
  return httpRequest<AgricultureGrowthStage>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/growth-stage`,
    { method: "POST", body: payload },
  );
}
export async function getAgricultureGrowthStage(
  runId: string,
): Promise<AgricultureGrowthStage> {
  return httpRequest<AgricultureGrowthStage>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/growth-stage`,
  );
}
export async function correctAgricultureGrowthStage(
  estimateId: string,
  payload: { human_stage: string; note?: string },
): Promise<AgricultureGrowthStage> {
  return httpRequest<AgricultureGrowthStage>(
    `/agriculture/growth-stage-estimates/${encodeURIComponent(estimateId)}/correction`,
    { method: "POST", body: payload },
  );
}
export async function processAgricultureYieldForecast(
  runId: string,
  payload: Record<string, unknown> = {},
): Promise<AgricultureYieldForecast> {
  return httpRequest<AgricultureYieldForecast>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/yield-forecast`,
    { method: "POST", body: payload },
  );
}
export async function getAgricultureYieldForecast(
  runId: string,
): Promise<AgricultureYieldForecast> {
  return httpRequest<AgricultureYieldForecast>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/yield-forecast`,
  );
}
export async function createAgricultureInspectionPlan(
  runId: string,
  payload: Record<string, unknown> = {},
): Promise<{
  status: string;
  actions: AgricultureInspectionAction[];
  rejected: Array<Record<string, unknown>>;
  constraints: Record<string, unknown>;
  source_count: number;
}> {
  return httpRequest(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/inspection-actions`,
    { method: "POST", body: payload },
  );
}
export async function listAgricultureInspectionActions(
  runId: string,
): Promise<AgricultureInspectionAction[]> {
  return httpRequest<AgricultureInspectionAction[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/inspection-actions`,
  );
}
export async function approveAgricultureInspectionAction(
  id: string,
  status: "approved" | "rejected",
  note?: string,
): Promise<AgricultureInspectionAction> {
  return httpRequest<AgricultureInspectionAction>(
    `/agriculture/inspection-actions/${encodeURIComponent(id)}/approval`,
    { method: "POST", body: { status, note } },
  );
}
export async function assignAgricultureInspectionAction(id: string, payload: { assigned_to_user_id?: number | null; due_at?: string | null; reason?: string }): Promise<AgricultureInspectionAction> {
  return httpRequest<AgricultureInspectionAction>(`/agriculture/inspection-actions/${encodeURIComponent(id)}/assignment`, { method: "PUT", body: payload });
}
export async function createAgriculturePrescription(
  runId: string,
  ruleId: string,
): Promise<AgriculturePrescription> {
  return httpRequest<AgriculturePrescription>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/prescription-drafts`,
    { method: "POST", body: { rule_id: ruleId, minimum_confidence: 0.6 } },
  );
}
export async function listAgriculturePrescriptions(
  runId: string,
): Promise<AgriculturePrescription[]> {
  return httpRequest<AgriculturePrescription[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/prescription-drafts`,
  );
}
export async function approveAgriculturePrescription(
  id: string,
  status: "approved" | "rejected",
  note?: string,
): Promise<AgriculturePrescription> {
  return httpRequest<AgriculturePrescription>(
    `/agriculture/prescription-drafts/${encodeURIComponent(id)}/approval`,
    { method: "POST", body: { status, note } },
  );
}
export async function createAgricultureExport(
  runId: string,
  payload: { artifact_kind: string; format: string; source_id?: string },
): Promise<AgricultureExport> {
  return httpRequest<AgricultureExport>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/exports`,
    { method: "POST", body: payload },
  );
}
export async function listAgricultureExports(
  runId: string,
): Promise<AgricultureExport[]> {
  return httpRequest<AgricultureExport[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/exports`,
  );
}
export async function getAgricultureExportDownload(
  id: string,
): Promise<{
  id: string;
  status: string;
  format: string;
  checksum: string;
  expires_at: string;
  download_url: string;
}> {
  return httpRequest(`/agriculture/exports/${encodeURIComponent(id)}/download`);
}
export async function runAgricultureAssistant(
  runId: string,
  payload: { task: string; question: string },
): Promise<AgricultureAssistantRun> {
  return httpRequest<AgricultureAssistantRun>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/assistant`,
    { method: "POST", body: payload },
  );
}
export async function listAgricultureAssistantRuns(
  runId: string,
): Promise<AgricultureAssistantRun[]> {
  return httpRequest<AgricultureAssistantRun[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/assistant`,
  );
}
export async function approveAgricultureAssistantRun(
  id: string,
  status: "approved" | "rejected",
  note?: string,
): Promise<AgricultureAssistantRun> {
  return httpRequest<AgricultureAssistantRun>(
    `/agriculture/assistant-runs/${encodeURIComponent(id)}/approval`,
    { method: "POST", body: { status, note } },
  );
}

export async function createAgricultureAnalysisRun(
  flightId: string,
): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/analysis-runs`,
    {
      method: "POST",
      body: {
        idempotency_key: `ui-${flightId}`,
        requested_analyses: [
          "quality",
          "canopy",
          "rows",
          "stand_count",
          "weed",
          "standing_water",
          "crop_health",
        ],
      },
    },
  );
}

export async function listAgricultureAnalysisRuns(
  flightId: string,
): Promise<AgricultureAnalysisRun[]> {
  return httpRequest<AgricultureAnalysisRun[]>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/analysis-runs`,
  );
}

export async function processAgricultureAnalysisRun(
  runId: string,
): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/process`,
    { method: "POST", body: { force: false, cluster_radius_m: 8 } },
  );
}
export async function cancelAgricultureAnalysisRun(
  runId: string,
): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
}
export async function replayAgricultureAnalysisRun(
  runId: string,
): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/replay`,
    { method: "POST" },
  );
}

export async function getAgricultureAnalysisQuality(
  runId: string,
): Promise<AgricultureAnalysisQuality> {
  return httpRequest<AgricultureAnalysisQuality>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/quality`,
  );
}

export async function retryAgricultureAnalysisStage(runId: string, stageName: string, reason?: string) {
  return httpRequest<{ run_id: string; stage_name: string; status: string; task_id: string }>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageName)}/retry`,
    { method: "POST", body: { idempotency_key: `stage-retry-${runId}-${stageName}`, reason } },
  );
}

export async function listAgricultureObservations(
  runId: string,
  filters?: {
    type?: string;
    minConfidence?: number;
    minSeverity?: number;
    trend?: string;
    detectedFrom?: string;
    detectedTo?: string;
    bbox?: [number, number, number, number];
    cursor?: string;
    limit?: number;
  },
): Promise<AgricultureObservation[]> {
  const page = await listAgricultureObservationPage(runId, filters);
  return page.items;
}

export async function listAgricultureObservationPage(
  runId: string,
  filters?: {
    type?: string;
    minConfidence?: number;
    minSeverity?: number;
    trend?: string;
    detectedFrom?: string;
    detectedTo?: string;
    bbox?: [number, number, number, number];
    cursor?: string;
    limit?: number;
  },
): Promise<AgricultureObservationPage> {
  const query = new URLSearchParams();
  if (filters?.type) query.set("observation_type", filters.type);
  if (filters?.minConfidence != null)
    query.set("min_confidence", String(filters.minConfidence));
  if (filters?.minSeverity != null)
    query.set("min_severity", String(filters.minSeverity));
  if (filters?.trend) query.set("trend", filters.trend);
  if (filters?.detectedFrom) query.set("detected_from", filters.detectedFrom);
  if (filters?.detectedTo) query.set("detected_to", filters.detectedTo);
  if (filters?.bbox) query.set("bbox", filters.bbox.join(","));
  if (filters?.cursor) query.set("cursor", filters.cursor);
  if (filters?.limit) query.set("limit", String(filters.limit));
  return httpRequest<AgricultureObservationPage>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/observations${query.size ? `?${query}` : ""}`,
  );
}

export async function reviewAgricultureObservation(
  id: string,
  payload: {
    status: "confirmed" | "rejected" | "relabelled";
    label?: string;
    note?: string;
  },
): Promise<AgricultureObservation> {
  return httpRequest<AgricultureObservation>(
    `/agriculture/observations/${encodeURIComponent(id)}/review`,
    { method: "POST", body: payload },
  );
}
export async function getAgricultureObservationEvidence(
  id: string,
): Promise<AgricultureObservationEvidence> {
  return httpRequest<AgricultureObservationEvidence>(
    `/agriculture/observations/${encodeURIComponent(id)}/evidence`,
  );
}

export async function initiateAgricultureUpload(
  flightId: string,
  payload: {
    source_kind:
      | "rgb_video"
      | "rgb_stills"
      | "multispectral"
      | "multispectral_band"
      | "thermal"
      | "orthomosaic";
    filename?: string;
    content_type?: string;
    total_bytes: number;
    checksum: string;
    metadata?: Record<string, unknown>;
  },
): Promise<AgricultureUploadSession> {
  return httpRequest<AgricultureUploadSession>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/uploads`,
    { method: "POST", body: payload },
  );
}

export async function uploadAgricultureChunk(
  session: AgricultureUploadSession,
  chunk: Blob,
  signal?: AbortSignal,
): Promise<AgricultureUploadSession> {
  return httpRequest<AgricultureUploadSession>(session.chunk_url, {
    method: "PUT",
    body: chunk,
    signal,
    headers: { "Upload-Offset": String(session.upload_offset) },
  });
}

export async function completeAgricultureUpload(
  flightId: string,
  uploadId: string,
): Promise<{
  id: string;
  upload_id: string;
  status: string;
  signed_url?: string;
}> {
  return httpRequest(
    `/agriculture/flights/${encodeURIComponent(flightId)}/uploads/${encodeURIComponent(uploadId)}/complete`,
    { method: "POST" },
  );
}

export async function retryAgricultureUpload(flightId: string, uploadId: string) {
  return httpRequest<{ id: string; status: string; upload_offset: number; total_bytes: number; chunk_bytes?: number; expires_at?: string; retryable: boolean }>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/uploads/${encodeURIComponent(uploadId)}/retry`,
    { method: "POST" },
  );
}

export async function reconcileAgricultureMedia(flightId: string) {
  return httpRequest<AgricultureMediaInventory>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/media-inventory/reconcile`,
    { method: "POST" },
  );
}

export async function getAgricultureAnalysisLayer(
  runId: string,
  layer: string,
): Promise<AgricultureLayer> {
  return httpRequest<AgricultureLayer>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/layers/${encodeURIComponent(layer)}`,
  );
}

export async function getAgricultureSpatialViewport(
  runId: string,
  options: { layer?: string; bbox?: string; zoom?: number; minSeverity?: number; minConfidence?: number } = {},
): Promise<AgricultureSpatialViewport> {
  const params = new URLSearchParams();
  if (options.layer) params.set("layer", options.layer);
  if (options.bbox) params.set("bbox", options.bbox);
  if (options.zoom != null) params.set("zoom", String(options.zoom));
  if (options.minSeverity != null) params.set("min_severity", String(options.minSeverity));
  if (options.minConfidence != null) params.set("min_confidence", String(options.minConfidence));
  return httpRequest<AgricultureSpatialViewport>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/spatial/viewport?${params.toString()}`);
}

export async function listAgricultureSpatialLayers(runId: string): Promise<AgricultureSpatialLayers> {
  return httpRequest<AgricultureSpatialLayers>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/spatial/layers`);
}

export async function listAgricultureTimeline(
  fieldId: number,
): Promise<AgricultureTimelineFlight[]> {
  return httpRequest<AgricultureTimelineFlight[]>(
    `/agriculture/fields/${fieldId}/timeline`,
  );
}
export async function listAgricultureFieldFlights(
  fieldId: number,
): Promise<AgricultureFlight[]> {
  return httpRequest<AgricultureFlight[]>(
    `/agriculture/fields/${fieldId}/flights`,
  );
}
export async function listAgricultureFieldOverviews(): Promise<
  AgricultureFieldOverview[]
> {
  return httpRequest<AgricultureFieldOverview[]>(
    "/agriculture/fields/overview",
  );
}
export async function getAgricultureAnalysisRun(
  runId: string,
): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}`,
  );
}
export async function compareAgricultureFlight(
  flightId: string,
  payload: { reference_flight_id?: string | null; min_quality_score?: number },
): Promise<AgricultureComparison> {
  return httpRequest<AgricultureComparison>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/compare`,
    { method: "POST", body: payload },
  );
}
export async function createAgricultureFieldComparison(
  fieldId: number,
  payload: {
    current_flight_id: string;
    reference_flight_id?: string | null;
    min_quality_score?: number;
  },
): Promise<AgricultureComparison> {
  return httpRequest<AgricultureComparison>(
    `/agriculture/fields/${fieldId}/comparisons`,
    { method: "POST", body: payload },
  );
}
export async function getAgricultureComparison(
  id: string,
): Promise<AgricultureComparison> {
  return httpRequest<AgricultureComparison>(
    `/agriculture/comparisons/${encodeURIComponent(id)}`,
  );
}
export async function startAgricultureFlight(
  payload: Record<string, unknown>,
): Promise<{
  flight_id: string;
  status: string;
  mission_name: string;
  mission_type: string;
  waypoints_count: number;
}> {
  return httpRequest("/agriculture/flights/start", {
    method: "POST",
    body: payload,
  });
}
export async function ingestAgricultureManifest(
  flightId: string,
  payload: {
    kind: "exif" | "sidecar" | "flight_manifest";
    idempotency_key: string;
    checksum: string;
    payload: Record<string, unknown>;
  },
): Promise<Record<string, unknown>> {
  return httpRequest(
    `/agriculture/flights/${encodeURIComponent(flightId)}/manifests`,
    { method: "POST", body: payload },
  );
}
export async function ingestAgricultureTelemetry(
  flightId: string,
  idempotencyKey: string,
  payload: Record<string, unknown>,
): Promise<{
  inserted: number;
  duplicates: number;
  rejected: number;
  gap_count: number;
}> {
  return httpRequest(
    `/agriculture/flights/${encodeURIComponent(flightId)}/telemetry`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: payload,
    },
  );
}
export async function listAgricultureComparisons(
  flightId: string,
): Promise<AgricultureChange[]> {
  return httpRequest<AgricultureChange[]>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/comparisons`,
  );
}
export async function listAgricultureObservationAudits(
  id: string,
): Promise<Array<Record<string, unknown>>> {
  return httpRequest<Array<Record<string, unknown>>>(
    `/agriculture/observations/${encodeURIComponent(id)}/audit`,
  );
}

export async function assignAgricultureObservation(id: string, payload: { assigned_to_user_id?: number | null; review_due_at?: string | null; reason?: string }): Promise<AgricultureObservation> {
  return httpRequest<AgricultureObservation>(`/agriculture/observations/${encodeURIComponent(id)}/assignment`, { method: "PUT", body: payload });
}
export async function listAgricultureObservationFeedback(id: string): Promise<AgricultureObservationFeedback[]> {
  return httpRequest<AgricultureObservationFeedback[]>(`/agriculture/observations/${encodeURIComponent(id)}/feedback`);
}
export async function submitAgricultureObservationFeedback(id: string, payload: Omit<AgricultureObservationFeedback, "id" | "observation_id" | "actor_user_id" | "status" | "decision_note" | "annotation_id" | "decided_at" | "created_at">): Promise<AgricultureObservationFeedback> {
  return httpRequest<AgricultureObservationFeedback>(`/agriculture/observations/${encodeURIComponent(id)}/feedback`, { method: "POST", body: payload });
}
export async function decideAgricultureObservationFeedback(id: string, payload: { status: "accepted" | "rejected"; note?: string }): Promise<AgricultureObservationFeedback> {
  return httpRequest<AgricultureObservationFeedback>(`/agriculture/feedback/${encodeURIComponent(id)}/decision`, { method: "POST", body: payload });
}
export async function createAgricultureObservationAlert(id: string, payload: { title: string; message: string; severity: "info" | "warning" | "critical"; due_at?: string | null }) {
  return httpRequest<{ alert: Record<string, unknown>; observation_id: string }>(`/agriculture/observations/${encodeURIComponent(id)}/alert`, { method: "POST", body: payload });
}
export async function createAgricultureAnnotation(
  id: string,
  payload: Omit<
    AgricultureAnnotation,
    | "id"
    | "observation_id"
    | "version"
    | "created_by_user_id"
    | "approved_by_user_id"
    | "created_at"
    | "updated_at"
  >,
): Promise<AgricultureAnnotation> {
  return httpRequest<AgricultureAnnotation>(
    `/agriculture/observations/${encodeURIComponent(id)}/annotations`,
    { method: "POST", body: payload },
  );
}
