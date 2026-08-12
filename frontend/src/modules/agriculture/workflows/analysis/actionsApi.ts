import { httpRequest } from "../../../../shared/api/httpClient";
import type {
  AgricultureFusionResult,
  AgricultureCropRisk,
  AgricultureGrowthMetric,
  AgricultureGrowthStage,
  AgricultureYieldForecast,
  AgricultureInspectionAction,
  AgriculturePrescription,
  AgricultureExport,
  AgricultureAssistantRun,
  AgricultureReport,
  AgricultureReportSnapshot,
  AgricultureModelVersion,
  AgricultureModelReleaseGate,
  FieldOutcome,
  RankedFindingPage,
} from "../../types";

export async function getAgricultureReport(runId: string): Promise<AgricultureReport> {
  return httpRequest<AgricultureReport>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/report`);
}

export async function createAgricultureReportSnapshot(
  runId: string,
  templateKey: "standard" | "executive" | "field_visit" | "decision" = "standard",
  comparisonId?: string,
): Promise<AgricultureReportSnapshot> {
  return httpRequest<AgricultureReportSnapshot>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/report-snapshots`, {
    method: "POST",
    body: { template_key: templateKey, ...(comparisonId ? { comparison_id: comparisonId } : {}) },
  });
}

export async function listAgricultureReportSnapshots(runId: string): Promise<AgricultureReportSnapshot[]> {
  return httpRequest<AgricultureReportSnapshot[]>(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/report-snapshots`);
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

export async function updateAgricultureInspectionRoute(
  runId: string,
  payload: { ordered_action_ids: string[]; removed_action_ids?: string[]; reason?: string },
): Promise<AgricultureInspectionAction[]> {
  return httpRequest<AgricultureInspectionAction[]>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/inspection-actions/route`,
    { method: "PUT", body: payload },
  );
}

export async function listAgricultureFindings(
  runId: string,
  options: { limit?: number; includeWithheld?: boolean } = {},
): Promise<RankedFindingPage> {
  const params = new URLSearchParams();
  if (options.limit != null) params.set("limit", String(options.limit));
  if (options.includeWithheld) params.set("include_withheld", "true");
  const query = params.toString();
  return httpRequest(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}/findings${query ? `?${query}` : ""}`,
  );
}

export async function mergeAgricultureFindings(
  runId: string,
  payload: { primary_observation_id: string; member_observation_ids: string[]; reason?: string },
) {
  return httpRequest(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/findings/merge`, {
    method: "POST",
    body: payload,
  });
}

export async function splitAgricultureFinding(
  observationId: string,
  payload: { parts: Array<Record<string, unknown>>; reason?: string },
) {
  return httpRequest(`/agriculture/observations/${encodeURIComponent(observationId)}/split`, {
    method: "POST",
    body: payload,
  });
}

export async function createAgricultureFieldOutcome(
  runId: string,
  payload: {
    observation_id: string;
    outcome_status: "confirmed_present" | "false_positive" | "treated" | "unresolved" | "other";
    notes?: string;
    model_version?: string;
    capability_release_id?: string;
  },
): Promise<FieldOutcome> {
  return httpRequest(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/field-outcomes`, {
    method: "POST",
    body: payload,
  });
}

export async function listAgricultureFieldOutcomes(runId: string): Promise<FieldOutcome[]> {
  return httpRequest(`/agriculture/analysis-runs/${encodeURIComponent(runId)}/field-outcomes`);
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

