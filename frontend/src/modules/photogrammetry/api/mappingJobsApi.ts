import { httpRequest } from "../../../shared/api/httpClient";
import type {
  MappingJobArtifacts,
  MappingJobRecord,
} from "../types";
import { FAST_3D_MAP_WEBODM_OPTIONS } from "../types";

export async function fetchMappingJob(
  jobId: number,
  token?: string | null,
): Promise<MappingJobRecord> {
  return httpRequest<MappingJobRecord>(`/mapping/jobs/${jobId}`, { token });
}

export async function listMappingJobs(token?: string | null): Promise<MappingJobRecord[]> {
  return httpRequest<MappingJobRecord[]>("/mapping/jobs", { token });
}

export async function deleteMappingJob(jobId: number, token?: string | null): Promise<void> {
  await httpRequest(`/mapping/jobs/${jobId}`, { method: "DELETE", token });
}

export async function startMappingJob(jobId: number, token?: string | null): Promise<void> {
  await httpRequest(`/mapping/jobs/${jobId}/start`, { method: "POST", token });
}

export type CreateMappingJobPayload = {
  field_id: number;
  processor: string;
  input_source: string;
  drone_sync?: { source_dir?: string; recursive: boolean };
  start_immediately?: boolean;
  artifacts: MappingJobArtifacts;
  webodm_options: typeof FAST_3D_MAP_WEBODM_OPTIONS;
};

export async function createMappingJob(
  payload: CreateMappingJobPayload,
  token?: string | null,
): Promise<{ job_id?: number }> {
  return httpRequest<{ job_id?: number }>("/mapping/jobs", {
    method: "POST",
    body: payload,
    token,
  });
}

export async function uploadMappingJobImages(
  jobId: number,
  files: File[],
  token?: string | null,
): Promise<void> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  await httpRequest(`/mapping/jobs/${jobId}/images`, {
    method: "POST",
    body: formData,
    token,
  });
}

export type UploadMappingJobPayload = {
  field_name?: string;
  artifacts: MappingJobArtifacts;
  webodm_options: typeof FAST_3D_MAP_WEBODM_OPTIONS;
};

export async function createMappingJobFromUpload(
  files: File[],
  payload: UploadMappingJobPayload,
  token?: string | null,
): Promise<MappingJobRecord> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (payload.field_name) {
    formData.append("field_name", payload.field_name);
  }
  formData.append("artifacts", JSON.stringify(payload.artifacts));
  formData.append("webodm_options", JSON.stringify(payload.webodm_options));
  return httpRequest<MappingJobRecord>("/mapping/jobs/upload", {
    method: "POST",
    body: formData,
    token,
  });
}
