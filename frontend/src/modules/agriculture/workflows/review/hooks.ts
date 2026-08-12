import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createAgricultureAnnotation,
  getAgricultureObservationEvidence,
  listAgricultureObservations,
  listAgricultureObservationPage,
  reviewAgricultureObservation,
  listAgricultureObservationAudits,
  assignAgricultureObservation,
  listAgricultureObservationFeedback,
  submitAgricultureObservationFeedback,
  decideAgricultureObservationFeedback,
  createAgricultureObservationAlert,
} from "../../api";
import { agricultureInvalidationKeys, agricultureKeys, agriculturePollInterval } from "../queryKeys";

export function useAgricultureObservationAudits(observationId: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "observation-audit", observationId],
    queryFn: () => listAgricultureObservationAudits(observationId as string),
    enabled: Boolean(observationId),
  });
}

export function useAgricultureObservationFeedback(observationId: string | null) {
  return useQuery({ queryKey: agricultureKeys.feedback(observationId), queryFn: () => listAgricultureObservationFeedback(observationId as string), enabled: Boolean(observationId) });
}

export function useAssignAgricultureObservation() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof assignAgricultureObservation>[1] }) => assignAgricultureObservation(id, payload), onSuccess: (observation) => { void client.invalidateQueries({ queryKey: agricultureKeys.observations(observation.run_id) }); } });
}

export function useSubmitAgricultureObservationFeedback() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof submitAgricultureObservationFeedback>[1] }) => submitAgricultureObservationFeedback(id, payload), onSuccess: (feedback) => { void client.invalidateQueries({ queryKey: agricultureKeys.feedback(feedback.observation_id) }); } });
}

export function useDecideAgricultureObservationFeedback() {
  const client = useQueryClient();
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof decideAgricultureObservationFeedback>[1] }) => decideAgricultureObservationFeedback(id, payload), onSuccess: (feedback) => { void client.invalidateQueries({ queryKey: agricultureKeys.feedback(feedback.observation_id) }); void client.invalidateQueries({ queryKey: agricultureKeys.observations(null) }); } });
}

export function useCreateAgricultureObservationAlert() {
  return useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof createAgricultureObservationAlert>[1] }) => createAgricultureObservationAlert(id, payload) });
}

export function useAgricultureObservations(
  runId: string | null,
  minConfidence = 0,
) {
  return useQuery({
    queryKey: [...agricultureKeys.observations(runId), minConfidence],
    queryFn: () =>
      listAgricultureObservations(runId as string, { minConfidence }),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureObservationPage(
  runId: string | null,
  filters: { minConfidence?: number; cursor?: string; limit?: number } = {},
) {
  return useQuery({
    queryKey: [
      ...agricultureKeys.observations(runId),
      "page",
      filters.minConfidence ?? 0,
      filters.cursor ?? null,
      filters.limit ?? 500,
    ],
    queryFn: () => listAgricultureObservationPage(runId as string, filters),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureObservationEvidence(
  observationId: string | null,
) {
  return useQuery({
    queryKey: agricultureKeys.evidence(observationId),
    queryFn: () => getAgricultureObservationEvidence(observationId as string),
    enabled: Boolean(observationId),
    staleTime: 30_000,
  });
}

export function useReviewAgricultureObservation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: Parameters<typeof reviewAgricultureObservation>[1];
    }) => reviewAgricultureObservation(id, payload),
    onMutate: async ({ id, payload }) => {
      const observationQueries = agricultureInvalidationKeys.observations();
      await client.cancelQueries({ queryKey: observationQueries });
      const snapshots = client.getQueriesData({
        queryKey: observationQueries,
      });
      client.setQueriesData(
        { queryKey: observationQueries },
        (value: unknown) =>
          Array.isArray(value)
            ? value.map((row) =>
                (row as { id: string }).id === id
                  ? {
                      ...row,
                      review_state: payload.status,
                      review_label: payload.label ?? null,
                      review_note: payload.note ?? null,
                    }
                  : row,
              )
            : value,
      );
      return { snapshots };
    },
    onError: (_error, _variables, context) => {
      context?.snapshots.forEach(([key, value]) =>
        client.setQueryData(key, value),
      );
    },
    onSuccess: (updated) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.observations(updated.run_id),
      });
      void client.invalidateQueries({
        queryKey: agricultureKeys.findings(updated.run_id),
      });
    },
  });
}

export function useCreateAgricultureAnnotation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      observationId,
      payload,
    }: {
      observationId: string;
      payload: Parameters<typeof createAgricultureAnnotation>[1];
    }) => createAgricultureAnnotation(observationId, payload),
    onSuccess: (annotation) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.evidence(annotation.observation_id),
      });
      void client.invalidateQueries({
        queryKey: agricultureInvalidationKeys.observations(),
      });
    },
  });
}
