export const visionKeys = {
  all: ["vision"] as const,
  projects: () => ["vision", "projects"] as const,
  datasetLists: () => ["vision", "datasets"] as const,
  datasets: (projectId: string) => ["vision", "datasets", projectId] as const,
  dataset: (datasetId: string) => ["vision", "dataset", datasetId] as const,
  images: (datasetId: string) => ["vision", "images", datasetId] as const,
  imagePage: (datasetId: string, offset: number) =>
    ["vision", "images", datasetId, offset] as const,
  models: () => ["vision", "models"] as const,
  trainingRuns: (projectId: string) =>
    ["vision", "training-runs", projectId] as const,
  training: (runId: string) => ["vision", "training", runId] as const,
  evaluation: (versionId: string) =>
    ["vision", "evaluation", versionId] as const,
};
