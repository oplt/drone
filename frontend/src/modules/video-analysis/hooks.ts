import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { videoAnalysisKeys } from "../../app/config/queryKeys";
import {
  getAnalysisJob,
  cancelVideoAnalysis,
  getAnalysisSummary,
  listDetections,
  listLiveSavedDetections,
  listMissionVideos,
  startVideoAnalysis,
  uploadVideo,
} from "./api";
import type {
  AnalyzeVideoPayload,
  VideoAnalysisJob,
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
    onSuccess: (_video, variables) => {
      void queryClient.invalidateQueries({
        queryKey: videoAnalysisKeys.videos(
          variables.missionId ?? null,
          variables.fieldId ?? null,
        ),
      });
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
    onSuccess: (job) =>
      queryClient.setQueryData(videoAnalysisKeys.job(job.id), job),
  });
}

export function useAnalysisJob(jobId: string | null) {
  return useQuery<VideoAnalysisJob>({
    queryKey: videoAnalysisKeys.job(jobId),
    queryFn: () => getAnalysisJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      isActive(query.state.data?.status) && isDocumentVisible() ? 1200 : false,
  });
}

export function useCancelAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: cancelVideoAnalysis,
    onSuccess: (job) => queryClient.setQueryData(videoAnalysisKeys.job(job.id), job),
  });
}

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
      const previous = queryClient.getQueryData<VideoDetectionPage>(queryKey);
      const last = previous?.items.at(-1);
      const page = await listDetections(jobId as string, {
        sinceId: last?.id,
      });
      if (!previous || !last) return page;
      const byId = new Map(previous.items.map((item) => [item.id, item]));
      page.items.forEach((item) => byId.set(item.id, item));
      return { ...page, items: [...byId.values()] };
    },
    enabled,
    refetchInterval: (query) =>
      isDocumentVisible() &&
      (isActive(status) || query.state.data?.has_more)
        ? 1500
        : false,
  });
}

export function useAnalysisSummary(jobId: string | null, status?: string) {
  return useQuery({
    queryKey: [...videoAnalysisKeys.job(jobId), "summary"],
    queryFn: () => getAnalysisSummary(jobId as string),
    enabled: Boolean(jobId) && status === "completed",
  });
}

export function useLiveSavedDetections() {
  return useQuery({
    queryKey: videoAnalysisKeys.liveDetections(),
    queryFn: listLiveSavedDetections,
    refetchInterval: isDocumentVisible() ? 2000 : false,
  });
}
