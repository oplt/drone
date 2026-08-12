import { httpRequest, resolveApiUrl } from "../../shared/api/httpClient";
import type {
  AnnotationInput,
  ExtractFramesResult,
  ModelEvaluation,
  VisionDataset,
  VisionImage,
  VisionImagePage,
  VisionModelVersion,
  VisionProject,
  VisionTrainingRun,
  VisionUploadResult,
} from "./visionTypes";

export type CreateVisionProjectInput = {
  name: string;
  crop: string;
  description?: string;
  classes: Array<{ name: string }>;
};

export type StartTrainingInput = {
  dataset_id: string;
  base_model: "yolo26n.pt" | "yolo26s.pt";
  preset: "fast" | "balanced" | "high_accuracy";
};

export const listVisionProjects = () =>
  httpRequest<VisionProject[]>("/vision/projects");

export const createVisionProject = (payload: CreateVisionProjectInput) =>
  httpRequest<VisionProject>("/vision/projects", {
    method: "POST",
    body: payload,
  });

export const createVisionDataset = (projectId: string) =>
  httpRequest<VisionDataset>(`/vision/projects/${projectId}/datasets`, {
    method: "POST",
  });

export const listVisionDatasets = (projectId: string) =>
  httpRequest<VisionDataset[]>(`/vision/projects/${projectId}/datasets`);

export const getVisionDataset = (datasetId: string) =>
  httpRequest<VisionDataset>(`/vision/datasets/${datasetId}`);

export const listVisionImages = (datasetId: string, offset = 0, limit = 200) =>
  httpRequest<VisionImagePage>(
    `/vision/datasets/${datasetId}/images?offset=${offset}&limit=${limit}`,
  );

export const uploadVisionImages = (datasetId: string, files: File[]) => {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  return httpRequest<VisionUploadResult>(
    `/vision/datasets/${datasetId}/images`,
    {
      method: "POST",
      body,
    },
  );
};

export const extractVisionFrames = (
  datasetId: string,
  payload: { video_id: string; interval_seconds: number; max_frames?: number },
) =>
  httpRequest<ExtractFramesResult>(
    `/vision/datasets/${datasetId}/extract-frames`,
    {
      method: "POST",
      body: payload,
    },
  );

export const saveVisionAnnotations = (
  imageId: string,
  annotations: AnnotationInput[],
  reviewed: boolean,
) =>
  httpRequest<VisionImage>(`/vision/images/${imageId}/annotations`, {
    method: "PUT",
    body: { annotations, reviewed },
  });

export const setVisionImageSelected = (imageId: string, selected: boolean) =>
  httpRequest<VisionImage>(`/vision/images/${imageId}`, {
    method: "PATCH",
    body: { selected },
  });

export const listVisionTrainingRuns = (projectId: string) =>
  httpRequest<VisionTrainingRun[]>(
    `/vision/projects/${projectId}/training-runs`,
  );

export const startVisionTraining = (
  projectId: string,
  payload: StartTrainingInput,
) =>
  httpRequest<VisionTrainingRun>(
    `/vision/projects/${projectId}/training-runs`,
    {
      method: "POST",
      body: payload,
    },
  );

export const getVisionTraining = (runId: string) =>
  httpRequest<VisionTrainingRun>(`/vision/training-runs/${runId}`);

export const cancelVisionTraining = (runId: string) =>
  httpRequest<VisionTrainingRun>(`/vision/training-runs/${runId}/cancel`, {
    method: "POST",
  });

export const listVisionModels = () =>
  httpRequest<VisionModelVersion[]>("/vision/models");

export const getModelEvaluation = (versionId: string) =>
  httpRequest<ModelEvaluation>(
    `/vision/model-versions/${versionId}/evaluation`,
  );

export const deployModelVersion = (versionId: string) =>
  httpRequest<VisionModelVersion>(
    `/vision/model-versions/${versionId}/deploy`,
    {
      method: "POST",
    },
  );

export const archiveModelVersion = (versionId: string) =>
  httpRequest<VisionModelVersion>(
    `/vision/model-versions/${versionId}/archive`,
    {
      method: "POST",
    },
  );

export const resolveVisionMediaUrl = (path: string) => resolveApiUrl(path);
