import { httpRequest } from "../../../shared/api/httpClient";

export async function fetchMissionDetail<T>(flightId: string, token?: string | null): Promise<T> {
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
  return httpRequest<T[]>(`/tasks/missions/${flightId}/transitions`, { token });
}

export async function fetchMissionCommands<T>(
  flightId: string,
  token?: string | null,
): Promise<T[]> {
  return httpRequest<T[]>(`/tasks/missions/${flightId}/commands`, { token });
}

export async function fetchMissionEvents<T>(flightId: string, token?: string | null): Promise<T[]> {
  return httpRequest<T[]>(`/tasks/missions/${flightId}/events`, { token });
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
  return httpRequest<T>(`/tasks/missions/${flightId}/export/${jobId}`, { token });
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
