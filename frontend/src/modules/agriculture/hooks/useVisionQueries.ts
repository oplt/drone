import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getModelEvaluation,
  getVisionDataset,
  getVisionTraining,
  listVisionDatasets,
  listVisionImages,
  listVisionModels,
  listVisionProjects,
  listVisionTrainingRuns,
} from "../visionApi";
import { visionKeys } from "./visionQueryKeys";
import { useVisionTrainingEvents } from "./useLifecycleEvents";

export const useVisionProjects = () =>
  useQuery({ queryKey: visionKeys.projects(), queryFn: listVisionProjects });
export const useVisionModels = () =>
  useQuery({ queryKey: visionKeys.models(), queryFn: listVisionModels, staleTime: 30_000 });
export const useVisionDatasets = (projectId: string | null) =>
  useQuery({
    queryKey: visionKeys.datasets(projectId ?? ""),
    queryFn: () => listVisionDatasets(projectId as string),
    enabled: Boolean(projectId),
  });
export const useVisionDataset = (datasetId: string | null) =>
  useQuery({
    queryKey: visionKeys.dataset(datasetId ?? ""),
    queryFn: () => getVisionDataset(datasetId as string),
    enabled: Boolean(datasetId),
  });
export const useVisionImages = (datasetId: string | null, offset = 0) =>
  useQuery({
    queryKey: visionKeys.imagePage(datasetId ?? "", offset),
    queryFn: () => listVisionImages(datasetId as string, offset),
    enabled: Boolean(datasetId),
  });
export const useVisionTrainingRuns = (projectId: string | null) => {
  const eventConnection = useVisionTrainingEvents(projectId);
  return useQuery({
    queryKey: visionKeys.trainingRuns(projectId ?? ""),
    queryFn: () => listVisionTrainingRuns(projectId as string),
    enabled: Boolean(projectId),
    refetchInterval: (query) =>
      query.state.data?.some((run) => ["queued", "running", "cancelling"].includes(run.status))
        ? eventConnection === "open" ? 30_000 : 2000
        : false,
  });
};
export const useVisionTraining = (runId: string | null) => {
  const queryClient = useQueryClient();
  const cached = queryClient.getQueryData<Awaited<ReturnType<typeof getVisionTraining>>>(
    visionKeys.training(runId ?? ""),
  );
  const eventConnection = useVisionTrainingEvents(cached?.project_id ?? null);
  return useQuery({
    queryKey: visionKeys.training(runId ?? ""),
    queryFn: () => getVisionTraining(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (current) =>
      ["queued", "running", "cancelling"].includes(current.state.data?.status ?? "")
        ? eventConnection === "open" ? 30_000 : 3000
        : false,
  });
};
export const useModelEvaluation = (versionId: string | null) =>
  useQuery({
    queryKey: visionKeys.evaluation(versionId ?? ""),
    queryFn: () => getModelEvaluation(versionId as string),
    enabled: Boolean(versionId),
  });
