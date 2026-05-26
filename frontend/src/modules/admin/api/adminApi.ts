import { httpRequest } from "../../../shared/api/httpClient";

export async function fetchAdminUsers<T = unknown>(token?: string | null): Promise<T> {
  return httpRequest<T>("/admin/users?page_size=100", { token });
}

export async function updateUserRole(
  userId: number,
  role: string,
  token?: string | null,
): Promise<void> {
  await httpRequest(`/admin/users/${userId}/role`, {
    method: "PUT",
    body: { role },
    token,
  });
}

export async function fetchAdminOrganizations<T = unknown>(token?: string | null): Promise<T> {
  return httpRequest<T>("/admin/organizations", { token });
}

export async function fetchAdminMappingJobs<T = unknown>(token?: string | null): Promise<T> {
  return httpRequest<T>("/admin/mapping-jobs?page_size=100", { token });
}

export async function requeueMappingJob(jobId: number, token?: string | null): Promise<void> {
  await httpRequest(`/admin/mapping-jobs/${jobId}/requeue`, {
    method: "POST",
    token,
  });
}

export async function fetchAdminExportJobs<T = unknown>(token?: string | null): Promise<T> {
  return httpRequest<T>("/admin/export-jobs?page_size=100", { token });
}

export async function fetchAdminWorkerHealth<T = unknown>(token?: string | null): Promise<T> {
  return httpRequest<T>("/admin/worker-health", { token });
}
