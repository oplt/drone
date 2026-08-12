import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createVisionDataset,
  createVisionProject,
  extractVisionFrames,
  uploadVisionImages,
} from "../visionApi";
import { visionKeys } from "./visionQueryKeys";

export function useCreateVisionProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createVisionProject,
    onSuccess: () => client.invalidateQueries({ queryKey: visionKeys.projects() }),
  });
}
export function useCreateVisionDataset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createVisionDataset,
    onSuccess: (_dataset, projectId) => Promise.all([
      client.invalidateQueries({ queryKey: visionKeys.datasets(projectId) }),
      client.invalidateQueries({ queryKey: visionKeys.projects() }),
    ]),
  });
}
export function useUploadVisionImages(datasetId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadVisionImages(datasetId, files),
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: visionKeys.images(datasetId) }),
      client.invalidateQueries({ queryKey: visionKeys.dataset(datasetId) }),
      client.invalidateQueries({ queryKey: visionKeys.datasetLists() }),
    ]),
  });
}
export function useExtractVisionFrames(datasetId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { video_id: string; interval_seconds: number; max_frames?: number }) =>
      extractVisionFrames(datasetId, payload),
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: visionKeys.images(datasetId) }),
      client.invalidateQueries({ queryKey: visionKeys.dataset(datasetId) }),
      client.invalidateQueries({ queryKey: visionKeys.datasetLists() }),
    ]),
  });
}
