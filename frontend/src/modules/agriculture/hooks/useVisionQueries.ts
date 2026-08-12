import { useQuery } from "@tanstack/react-query";
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
export const useVisionTrainingRuns = (projectId: string | null) =>
  useQuery({
    queryKey: visionKeys.trainingRuns(projectId ?? ""),
    queryFn: () => listVisionTrainingRuns(projectId as string),
    enabled: Boolean(projectId),
    refetchInterval: (query) =>
      query.state.data?.some((run) => ["queued", "running", "cancelling"].includes(run.status)) ? 2000 : false,
  });
export const useVisionTraining = (runId: string | null) =>
  useQuery({
    queryKey: visionKeys.training(runId ?? ""),
    queryFn: () => getVisionTraining(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => ["queued", "running", "cancelling"].includes(query.state.data?.status ?? "") ? 1500 : false,
  });
export const useModelEvaluation = (versionId: string | null) =>
  useQuery({
    queryKey: visionKeys.evaluation(versionId ?? ""),
    queryFn: () => getModelEvaluation(versionId as string),
    enabled: Boolean(versionId),
  });
