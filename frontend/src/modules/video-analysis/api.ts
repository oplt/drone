import { httpRequest, resolveApiUrl } from "../../shared/api/httpClient";
import type {
  AnalyzeVideoPayload,
  LiveSavedDetection,
  VideoAnalysisJob,
  VideoAsset,
  VideoDetection,
} from "./types";

export type ListMissionVideosParams = {
  missionId?: string | null;
  fieldId?: number | null;
  limit?: number;
};

export async function listMissionVideos(
  params: ListMissionVideosParams = {},
): Promise<VideoAsset[]> {
  const search = new URLSearchParams();
  if (params.missionId) search.set("mission_id", params.missionId);
  if (params.fieldId != null) search.set("field_id", String(params.fieldId));
  if (params.limit != null) search.set("limit", String(params.limit));
  const query = search.toString();
  return httpRequest<VideoAsset[]>(`/video-analysis/videos${query ? `?${query}` : ""}`);
}

export function buildMissionVideoStreamUrl(videoId: string, token?: string | null): string {
  const base = resolveApiUrl(`/video-analysis/videos/${videoId}/stream`);
  if (!token?.trim()) return base;
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}token=${encodeURIComponent(token.trim())}`;
}

export async function uploadVideo(
  file: File,
  options?: { missionId?: string | null; fieldId?: number | null },
): Promise<VideoAsset> {
  const form = new FormData();
  form.append("file", file);
  if (options?.missionId) form.append("mission_id", options.missionId);
  if (options?.fieldId != null) form.append("field_id", String(options.fieldId));
  return httpRequest<VideoAsset>("/video-analysis/videos", { method: "POST", body: form });
}

export async function startVideoAnalysis(
  videoId: string,
  payload: AnalyzeVideoPayload,
): Promise<VideoAnalysisJob> {
  return httpRequest<VideoAnalysisJob>(`/video-analysis/videos/${videoId}/analyze`, {
    method: "POST",
    body: payload,
  });
}

export async function getAnalysisJob(jobId: string): Promise<VideoAnalysisJob> {
  return httpRequest<VideoAnalysisJob>(`/video-analysis/jobs/${jobId}`);
}

export async function listDetections(jobId: string): Promise<VideoDetection[]> {
  return httpRequest<VideoDetection[]>(`/video-analysis/jobs/${jobId}/detections?limit=2000`);
}

export async function listLiveSavedDetections(): Promise<LiveSavedDetection[]> {
  return httpRequest<LiveSavedDetection[]>("/api/live-object-detection/detections?limit=500");
}
