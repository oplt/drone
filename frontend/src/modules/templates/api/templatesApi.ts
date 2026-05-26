import { httpRequest } from "../../../shared/api/httpClient";
import type { MissionTemplate } from "../types";

export async function fetchTemplates(token?: string | null): Promise<MissionTemplate[]> {
  const data = await httpRequest<{ items: MissionTemplate[] } | MissionTemplate[]>(
    "/tasks/templates",
    { token },
  );
  return Array.isArray(data) ? data : data.items ?? [];
}

export async function createTemplate(
  payload: {
    name: string;
    mission_type: string;
    schedule_cron: string | null;
  },
  token?: string | null,
): Promise<MissionTemplate> {
  return httpRequest<MissionTemplate>("/tasks/templates", {
    method: "POST",
    body: { ...payload, config: {}, preflight_profile: {} },
    token,
  });
}

export async function triggerTemplate(
  id: number,
  token?: string | null,
): Promise<{ run_id: number }> {
  return httpRequest<{ run_id: number }>(`/tasks/templates/${id}/trigger`, {
    method: "POST",
    token,
  });
}

export async function toggleTemplate(
  id: number,
  is_active: boolean,
  token?: string | null,
): Promise<void> {
  await httpRequest(`/tasks/templates/${id}`, {
    method: "PATCH",
    body: { is_active },
    token,
  });
}
