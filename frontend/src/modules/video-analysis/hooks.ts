import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { videoAnalysisKeys } from "../../app/config/queryKeys";
import {
  getAnalysisJob,
  cancelVideoAnalysis,
  getAnalysisSummary,
  getDetectionAggregates,
  listDetections,
  listLiveSavedDetections,
  listMissionVideos,
  patchCaptureMetadata,
  startVideoAnalysis,
  uploadVideo,
} from "./api";
import type {
  AnalyzeVideoPayload,
  VideoCaptureMetadataPatch,
  VideoDetectionPage,
} from "./types";

const isActive = (status?: string): boolean =>
  status === "queued" || status === "running";
const isDocumentVisible = (): boolean =>
  typeof document === "undefined" || document.visibilityState === "visible";

type UploadVideoInput = {
  file: File;
  missionId?: string | null;
  fieldId?: number | null;
};

export function useMissionVideos(
  missionId: string | null,
  fieldId: number | null,
  options?: { flightActive?: boolean; enabled?: boolean },
) {
  const enabled = options?.enabled ?? Boolean(missionId || fieldId != null);
  return useQuery({
    queryKey: videoAnalysisKeys.videos(missionId, fieldId),
    queryFn: () =>
      listMissionVideos({
        missionId: missionId ?? undefined,
        fieldId: fieldId ?? undefined,
      }),
    enabled,
    refetchInterval:
      options?.flightActive && isDocumentVisible() ? 5000 : false,
  });
}

export function useUploadVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, missionId, fieldId }: UploadVideoInput) =>
      uploadVideo(file, { missionId, fieldId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: videoAnalysisKeys.all });
    },
  });
}

export function useStartAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      videoId,
      payload,
    }: {
      videoId: string;
      payload: AnalyzeVideoPayload;
    }) => startVideoAnalysis(videoId, payload),
    onSuccess: (job) => {
      queryClient.setQueryData(videoAnalysisKeys.job(job.id), job);
    },
  });
}

export function useAnalysisJob(jobId: string | null) {
  return useQuery({
    queryKey: videoAnalysisKeys.job(jobId),
    queryFn: () => getAnalysisJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      isDocumentVisible() && isActive(query.state.data?.status) ? 1500 : false,
  });
}

export function useCancelAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: cancelVideoAnalysis,
    onSuccess: (job) => queryClient.setQueryData(videoAnalysisKeys.job(job.id), job),
  });
}

/** Live jobs: delta-accumulate. Completed: one page only (timeline uses aggregates). */
export function useDetections(jobId: string | null, status?: string) {
  const queryClient = useQueryClient();
  const queryKey = videoAnalysisKeys.detections(jobId);
  const enabled =
    Boolean(jobId) &&
    Boolean(status) &&
    status !== "queued" &&
    status !== "failed";
  return useQuery({
    queryKey,
    queryFn: async () => {
      if (!isActive(status)) {
        return listDetections(jobId as string, { limit: 250 });
      }
      const previous = queryClient.getQueryData<VideoDetectionPage>(queryKey);
      const last = previous?.items.at(-1);
      const page = await listDetections(jobId as string, {
        sinceId: last?.id,
        limit: 250,
      });
      if (!previous || !last) return page;
      const byId = new Map(previous.items.map((item) => [item.id, item]));
      page.items.forEach((item) => byId.set(item.id, item));
      return { ...page, items: [...byId.values()] };
    },
    enabled,
    refetchInterval: (query) =>
      isDocumentVisible() &&
      (isActive(status) || Boolean(query.state.data?.has_more && isActive(status)))
        ? 1500
        : false,
  });
}

export function useDetectionAggregates(
  jobId: string | null,
  status?: string,
  durationSeconds = 1,
) {
  const bucketSeconds = Math.max(1, durationSeconds / 100);
  return useQuery({
    queryKey: videoAnalysisKeys.detectionAggregates(jobId, bucketSeconds),
    queryFn: () =>
      getDetectionAggregates(jobId as string, { bucketSeconds }),
    enabled:
      Boolean(jobId) &&
      Boolean(status) &&
      status !== "queued" &&
      status !== "failed",
    refetchInterval: () =>
      isDocumentVisible() && isActive(status) ? 2000 : false,
  });
}

export function useDetectionWindow(
  jobId: string | null,
  window: { sinceTs: number; untilTs: number } | null,
) {
  return useQuery({
    queryKey: videoAnalysisKeys.detectionWindow(
      jobId,
      window?.sinceTs ?? null,
      window?.untilTs ?? null,
    ),
    queryFn: () =>
      listDetections(jobId as string, {
        sinceTs: window!.sinceTs,
        untilTs: window!.untilTs,
        limit: 100,
      }),
    enabled: Boolean(jobId && window),
  });
}

export function useAnalysisSummary(jobId: string | null, status?: string) {
  return useQuery({
    queryKey: [...videoAnalysisKeys.job(jobId), "summary"],
    queryFn: () => getAnalysisSummary(jobId as string),
    enabled: Boolean(jobId) && status === "completed",
  });
}

export function usePatchCaptureMetadata() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      videoId,
      patch,
    }: {
      videoId: string;
      patch: VideoCaptureMetadataPatch;
    }) => patchCaptureMetadata(videoId, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: videoAnalysisKeys.all });
    },
  });
}

export function useLiveSavedDetections() {
  return useQuery({
    queryKey: videoAnalysisKeys.liveDetections(),
    queryFn: listLiveSavedDetections,
    refetchInterval: isDocumentVisible() ? 2000 : false,
  });
}
