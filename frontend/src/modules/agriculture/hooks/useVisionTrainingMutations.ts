import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  archiveModelVersion,
  cancelVisionTraining,
  deployModelVersion,
  startVisionTraining,
} from "../visionApi";
import type { VisionTrainingRun } from "../visionTypes";
import { visionKeys } from "./visionQueryKeys";

export function useStartVisionTraining() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, payload }: { projectId: string; payload: Parameters<typeof startVisionTraining>[1] }) =>
      startVisionTraining(projectId, payload),
    onSuccess: (run) => client.setQueryData<VisionTrainingRun[]>(
      visionKeys.trainingRuns(run.project_id),
      (runs) => [run, ...(runs ?? []).filter((item) => item.id !== run.id)],
    ),
  });
}
export function useCancelVisionTraining() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: cancelVisionTraining,
    onSuccess: (run) => {
      client.setQueryData(visionKeys.training(run.id), run);
      void client.invalidateQueries({ queryKey: visionKeys.trainingRuns(run.project_id) });
    },
  });
}
export function useDeployModelVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: deployModelVersion,
    onSuccess: () => client.invalidateQueries({ queryKey: visionKeys.models() }),
  });
}
export function useArchiveModelVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: archiveModelVersion,
    onSuccess: () => client.invalidateQueries({ queryKey: visionKeys.models() }),
  });
}
