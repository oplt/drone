import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { videoAnalysisKeys } from "../../app/config/queryKeys";
import {
  getAnalysisJob,
  listDetections,
  listLiveSavedDetections,
  startVideoAnalysis,
  uploadVideo,
} from "./api";
import type { AnalyzeVideoPayload, VideoAnalysisJob } from "./types";

const isActive = (status?: string): boolean => status === "queued" || status === "running";

export function useUploadVideo() {
  return useMutation({ mutationFn: (file: File) => uploadVideo(file) });
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
