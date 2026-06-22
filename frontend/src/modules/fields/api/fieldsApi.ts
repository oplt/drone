import { httpRequest } from "../../../shared/api/httpClient";
import type { FieldCreateDTO, FieldOutDTO, LonLat } from "../types";
import type { FieldFeature } from "../types";
import type { FieldWorkflowScope } from "../constants";
import { parseFieldFeatures } from "../utils/fieldGeometry";

export async function fetchFieldFeatures(
  options?: { workflowScope?: FieldWorkflowScope | null; token?: string | null },
): Promise<FieldFeature[]> {
  const workflowScope = options?.workflowScope;
  const token = options?.token;
  const query =
    workflowScope != null
      ? `?workflow_scope=${encodeURIComponent(workflowScope)}`
      : "";
  const fc = await httpRequest<{ features?: unknown[] }>(`/fields/features${query}`, { token });
  return parseFieldFeatures(fc as Parameters<typeof parseFieldFeatures>[0]);
}

export async function createField(
  payload: FieldCreateDTO,
  token?: string | null,
): Promise<FieldOutDTO> {
  return httpRequest<FieldOutDTO>("/fields", {
    method: "POST",
    body: payload,
    token,
  });
}

export async function updateField(
  fieldId: number,
  payload: { name: string; coordinates: LonLat[] },
  token?: string | null,
): Promise<FieldOutDTO> {
  return httpRequest<FieldOutDTO>(`/fields/${fieldId}`, {
    method: "PATCH",
    body: payload,
    token,
  });
}

export async function deleteField(fieldId: number, token?: string | null): Promise<void> {
  await httpRequest(`/fields/${fieldId}`, { method: "DELETE", token });
}
