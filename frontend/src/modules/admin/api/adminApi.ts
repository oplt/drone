import {
  httpRequest,
  resolveApiUrl,
  shouldAttachBearerToken,
} from "../../../shared/api/httpClient";

export type AdminRuntimeLogFile = {
  source: string;
  relative_path: string;
  size_bytes: number;
  modified_at: string;
  legacy: boolean;
};

export type AdminRuntimeLogsResponse = {
  runtime_log_root: string;
  logs: AdminRuntimeLogFile[];
};

export async function fetchAdminUsers<T = unknown>(
  token?: string | null,
): Promise<T> {
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

export async function fetchAdminOrganizations<T = unknown>(
  token?: string | null,
): Promise<T> {
  return httpRequest<T>("/admin/organizations?page_size=100", { token });
}

export async function fetchAdminMappingJobs<T = unknown>(
  token?: string | null,
): Promise<T> {
  return httpRequest<T>("/admin/mapping-jobs?page_size=100", { token });
}

export async function requeueMappingJob(
  jobId: number,
  token?: string | null,
): Promise<void> {
  await httpRequest(`/admin/mapping-jobs/${jobId}/requeue`, {
    method: "POST",
    token,
  });
}

export async function fetchAdminExportJobs<T = unknown>(
  token?: string | null,
): Promise<T> {
  return httpRequest<T>("/admin/export-jobs?page_size=100", { token });
}

export async function fetchAdminWorkerHealth<T = unknown>(
  token?: string | null,
): Promise<T> {
  return httpRequest<T>("/admin/worker-health", { token });
}

export async function fetchAdminRuntimeLogs(
  token?: string | null,
): Promise<AdminRuntimeLogsResponse> {
  return httpRequest<AdminRuntimeLogsResponse>("/admin/diagnostics/logs", {
    token,
  });
}

function filenameFromDisposition(disposition: string | null): string {
  const match = disposition?.match(/filename="?([^";]+)"?/);
  return match?.[1] ?? "drone-diagnostics.zip";
}

export async function downloadAdminDiagnosticsBundle(
  token?: string | null,
): Promise<void> {
  const headers = new Headers();
  if (shouldAttachBearerToken(token)) {
    headers.set("Authorization", `Bearer ${token?.trim()}`);
  }
  const response = await fetch(resolveApiUrl("/admin/diagnostics/bundle"), {
    method: "GET",
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    throw new Error("Diagnostics bundle could not be downloaded");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filenameFromDisposition(
    response.headers.get("content-disposition"),
  );
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
