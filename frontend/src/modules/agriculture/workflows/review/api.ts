import { httpRequest } from "../../../../shared/api/httpClient";
import type {
  AgricultureObservation,
  AgricultureObservationPage,
  AgricultureAnnotation,
  AgricultureObservationEvidence,
  AgricultureObservationFeedback,
} from "../../types";

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
