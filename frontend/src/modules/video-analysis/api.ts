import { httpRequest, resolveApiUrl } from "../../shared/api/httpClient";
import type {
  AnalyzeVideoPayload,
  LiveSavedDetection,
  VideoAnalysisJob,
  VideoAnalysisSummary,
  VideoAsset,
  VideoCaptureMetadataPatch,
  VideoDetectionAggregate,
  VideoDetectionPage,
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
  return httpRequest<VideoAsset[]>(
    `/video-analysis/videos${query ? `?${query}` : ""}`,
  );
}

export function buildMissionVideoStreamUrl(
  videoId: string,
  _token?: string | null,
): string {
  return resolveApiUrl(`/video-analysis/videos/${videoId}/stream`);
}

export async function uploadVideo(
  file: File,
  options?: { missionId?: string | null; fieldId?: number | null },
): Promise<VideoAsset> {
  const form = new FormData();
  form.append("file", file);
  if (options?.missionId) form.append("mission_id", options.missionId);
  if (options?.fieldId != null)
    form.append("field_id", String(options.fieldId));
  return httpRequest<VideoAsset>("/video-analysis/videos", {
    method: "POST",
    body: form,
  });
}

export async function startVideoAnalysis(
  videoId: string,
  payload: AnalyzeVideoPayload,
): Promise<VideoAnalysisJob> {
  return httpRequest<VideoAnalysisJob>(
    `/video-analysis/videos/${videoId}/analyze`,
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function getAnalysisJob(jobId: string): Promise<VideoAnalysisJob> {
  return httpRequest<VideoAnalysisJob>(`/video-analysis/jobs/${jobId}`);
}

export async function cancelVideoAnalysis(jobId: string): Promise<VideoAnalysisJob> {
  return httpRequest<VideoAnalysisJob>(`/video-analysis/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export async function listDetections(
  jobId: string,
  params: {
    cursor?: string | null;
    sinceId?: string | null;
    limit?: number;
    sinceTs?: number | null;
    untilTs?: number | null;
  } = {},
): Promise<VideoDetectionPage> {
  const search = new URLSearchParams({ limit: String(params.limit ?? 250) });
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.sinceId) search.set("since_id", params.sinceId);
  if (params.sinceTs != null) search.set("since_ts", String(params.sinceTs));
  if (params.untilTs != null) search.set("until_ts", String(params.untilTs));
  return httpRequest<VideoDetectionPage>(
    `/video-analysis/jobs/${jobId}/detections?${search}`,
  );
}

export async function getDetectionAggregates(
  jobId: string,
  params: { bucketSeconds?: number } = {},
): Promise<VideoDetectionAggregate> {
  const search = new URLSearchParams({
    bucket_seconds: String(params.bucketSeconds ?? 10),
  });
  return httpRequest<VideoDetectionAggregate>(
    `/video-analysis/jobs/${jobId}/detections/aggregate?${search}`,
  );
}

export async function patchCaptureMetadata(
  videoId: string,
  patch: VideoCaptureMetadataPatch,
): Promise<VideoAsset> {
  return httpRequest<VideoAsset>(
    `/video-analysis/videos/${videoId}/capture-metadata`,
    {
      method: "PATCH",
      body: patch,
    },
  );
}

export async function getAnalysisSummary(
  jobId: string,
): Promise<VideoAnalysisSummary> {
  return httpRequest<VideoAnalysisSummary>(
    `/video-analysis/jobs/${jobId}/summary`,
  );
}

export async function listLiveSavedDetections(): Promise<LiveSavedDetection[]> {
  return httpRequest<LiveSavedDetection[]>(
    "/api/live-object-detection/detections?limit=500",
  );
}
