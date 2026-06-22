import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { videoAnalysisKeys } from "../../app/config/queryKeys";
import {
  getAnalysisJob,
  listDetections,
  listLiveSavedDetections,
  listMissionVideos,
  startVideoAnalysis,
  uploadVideo,
} from "./api";
import type { AnalyzeVideoPayload, VideoAnalysisJob } from "./types";

const isActive = (status?: string): boolean => status === "queued" || status === "running";

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
    refetchInterval: options?.flightActive ? 5000 : false,
  });
}

export function useUploadVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, missionId, fieldId }: UploadVideoInput) =>
      uploadVideo(file, { missionId, fieldId }),
    onSuccess: (_video, variables) => {
      void queryClient.invalidateQueries({
        queryKey: videoAnalysisKeys.videos(variables.missionId ?? null, variables.fieldId ?? null),
      });
    },
  });
}

export function useStartAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ videoId, payload }: { videoId: string; payload: AnalyzeVideoPayload }) =>
      startVideoAnalysis(videoId, payload),
    onSuccess: (job) => queryClient.setQueryData(videoAnalysisKeys.job(job.id), job),
  });
}

export function useAnalysisJob(jobId: string | null) {
  return useQuery<VideoAnalysisJob>({
    queryKey: videoAnalysisKeys.job(jobId),
    queryFn: () => getAnalysisJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (isActive(query.state.data?.status) ? 1200 : false),
  });
}

export function useDetections(jobId: string | null, status?: string) {
  const enabled = Boolean(jobId) && Boolean(status) && status !== "queued" && status !== "failed";
  return useQuery({
    queryKey: videoAnalysisKeys.detections(jobId),
    queryFn: () => listDetections(jobId as string),
    enabled,
    refetchInterval: isActive(status) ? 1500 : false,
  });
}

export function useLiveSavedDetections() {
  return useQuery({
    queryKey: videoAnalysisKeys.liveDetections(),
    queryFn: listLiveSavedDetections,
    refetchInterval: 2000,
  });
}
