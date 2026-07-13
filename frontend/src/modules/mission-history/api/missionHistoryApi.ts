import { httpRequest } from "../../../shared/api/httpClient";
import { unwrapPage, type PageResponse } from "../../../shared/api/pagination";

export async function fetchMissionDetail<T>(
  flightId: string,
  token?: string | null,
): Promise<T> {
  return httpRequest<T>(`/tasks/missions/${flightId}`, { token });
}

export async function fetchMissionPreflight<T>(
  flightId: string,
  token?: string | null,
): Promise<T> {
  return httpRequest<T>(`/tasks/missions/${flightId}/preflight`, { token });
}

export async function fetchMissionTransitions<T>(
  flightId: string,
  token?: string | null,
): Promise<T[]> {
  return httpRequest<PageResponse<T>>(
    `/tasks/missions/${flightId}/transitions`,
    { token },
  ).then(unwrapPage);
}

export async function fetchMissionCommands<T>(
  flightId: string,
  token?: string | null,
): Promise<T[]> {
  return httpRequest<PageResponse<T>>(`/tasks/missions/${flightId}/commands`, {
    token,
  }).then(unwrapPage);
}

export async function fetchMissionEvents<T>(
  flightId: string,
  token?: string | null,
): Promise<T[]> {
  return httpRequest<PageResponse<T>>(`/tasks/missions/${flightId}/events`, {
    token,
  }).then(unwrapPage);
}

export async function fetchMissionCompliance<T>(
  flightId: string,
  token?: string | null,
): Promise<T> {
  return httpRequest<T>(`/tasks/missions/${flightId}/compliance`, { token });
}

export async function fetchMissionExportJob<T>(
  flightId: string,
  jobId: string,
  token?: string | null,
): Promise<T> {
  return httpRequest<T>(`/tasks/missions/${flightId}/export/${jobId}`, {
    token,
  });
}

export async function startMissionExport<T extends { job_id: number }>(
  flightId: string,
  token?: string | null,
): Promise<T> {
  return httpRequest<T>(`/tasks/missions/${flightId}/export`, {
    method: "POST",
    token,
  });
}
