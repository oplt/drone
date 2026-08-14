import { httpRequest } from "../../../../shared/api/httpClient";
import type {
  AgricultureAnalysisRun,
  AgricultureAnalysisQuality,
  AgricultureLayer,
  AgricultureChange,
  AgricultureComparison,
  AgricultureTimelineFlight,
  AgricultureUploadSession,
  AgricultureSpatialViewport,
  AgricultureSpatialLayers,
  AgricultureAnalysisReadiness,
} from "../../types";

function capabilityRequestKey(capabilities: string[]): string {
  const value = [...capabilities].sort().join("|");
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  }
  return (hash >>> 0).toString(36);
}

export async function getAgricultureAnalysisReadiness(
  flightId: string,
): Promise<AgricultureAnalysisReadiness> {
  return httpRequest<AgricultureAnalysisReadiness>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/analysis-readiness`,
  );
}

export async function createAgricultureAnalysisRun({
  flightId,
  requestedAnalyses,
}: {
  flightId: string;
  requestedAnalyses: string[];
}): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/analysis-runs`,
    {
      method: "POST",
      body: {
        idempotency_key: `ui-${flightId}-${capabilityRequestKey(requestedAnalyses)}`,
        requested_analyses: [...requestedAnalyses].sort(),
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
  options: { layer?: string; bbox?: string; zoom?: number; minSeverity?: number; minConfidence?: number; maxFeatures?: number } = {},
): Promise<AgricultureSpatialViewport> {
  const params = new URLSearchParams();
  if (options.layer) params.set("layer", options.layer);
  if (options.bbox) params.set("bbox", options.bbox);
  if (options.zoom != null) params.set("zoom", String(options.zoom));
  if (options.minSeverity != null) params.set("min_severity", String(options.minSeverity));
  if (options.minConfidence != null) params.set("min_confidence", String(options.minConfidence));
  if (options.maxFeatures != null) params.set("max_features", String(options.maxFeatures));
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

export async function getAgricultureAnalysisRun(
  runId: string,
): Promise<AgricultureAnalysisRun> {
  return httpRequest<AgricultureAnalysisRun>(
    `/agriculture/analysis-runs/${encodeURIComponent(runId)}`,
  );
}

export async function getAgricultureComparison(
  id: string,
): Promise<AgricultureComparison> {
  return httpRequest<AgricultureComparison>(
    `/agriculture/comparisons/${encodeURIComponent(id)}`,
  );
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

export async function listAgricultureComparisons(
  flightId: string,
): Promise<AgricultureChange[]> {
  return httpRequest<AgricultureChange[]>(
    `/agriculture/flights/${encodeURIComponent(flightId)}/comparisons`,
  );
}
