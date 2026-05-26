import { httpRequest } from "../../shared/api/httpClient";
import type {
  AnalyzeVideoPayload,
  LiveSavedDetection,
  VideoAnalysisJob,
  VideoAsset,
  VideoDetection,
} from "./types";

export async function uploadVideo(file: File): Promise<VideoAsset> {
  const form = new FormData();
  form.append("file", file);
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
