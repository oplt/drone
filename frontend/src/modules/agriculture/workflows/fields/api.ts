import { httpRequest } from "../../../../shared/api/httpClient";
import type {
  AgricultureFieldProfile,
  AgricultureFlight,
  AgricultureComparison,
  AgricultureFieldOverview,
  AgriculturePlan,
  AgriculturePlanRequest,
  AgriculturePreflightSnapshot,
  AgricultureFieldContext,
  AgricultureFieldZone,
} from "../../types";

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

export async function listAgricultureFieldPlans(fieldId: number): Promise<AgriculturePlan[]> {
  return httpRequest<AgriculturePlan[]>(`/agriculture/fields/${fieldId}/plans`);
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
