import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useWorkflowEventStream,
  type WorkflowEventConnection,
  type WorkflowEventEnvelope,
} from "../../../shared/api/useWorkflowEventStream";
import { agricultureKeys } from "../workflows/queryKeys";
import { visionKeys } from "./visionQueryKeys";

export function useAgricultureAnalysisEvents(
  runId: string | null,
): WorkflowEventConnection {
  const client = useQueryClient();
  const onEvent = useCallback(() => {
    if (!runId) return;
    void client.invalidateQueries({ queryKey: agricultureKeys.all });
  }, [client, runId]);
  return useWorkflowEventStream(
    runId
      ? `/agriculture/analysis-runs/${encodeURIComponent(runId)}/events`
      : null,
    onEvent,
  );
}

export function useVisionTrainingEvents(
  projectId: string | null,
): WorkflowEventConnection {
  const client = useQueryClient();
  const onEvent = useCallback(
    (event: WorkflowEventEnvelope) => {
      if (!projectId) return;
      void client.invalidateQueries({ queryKey: visionKeys.trainingRuns(projectId) });
      void client.invalidateQueries({ queryKey: visionKeys.training(event.subject_id) });
      if (event.event_type === "training.completed") {
        void client.invalidateQueries({ queryKey: visionKeys.models() });
      }
    },
    [client, projectId],
  );
  return useWorkflowEventStream(
    projectId
      ? `/vision/projects/${encodeURIComponent(projectId)}/training-events`
      : null,
    onEvent,
  );
}
