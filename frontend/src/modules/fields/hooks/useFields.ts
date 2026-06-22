import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { fieldsKeys } from "../../../app/config/queryKeys";
import { createField, deleteField, fetchFieldFeatures, updateField } from "../api/fieldsApi";
import type { FieldWorkflowScope } from "../constants";
import type { FieldCreateDTO, LonLat } from "../types";

export function useFields(workflowScope: FieldWorkflowScope) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: fieldsKeys.features(workflowScope),
    queryFn: () => fetchFieldFeatures({ workflowScope }),
  });

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: fieldsKeys.features(workflowScope) });
  }, [queryClient, workflowScope]);

  const createMutation = useMutation({
    mutationFn: (payload: FieldCreateDTO) =>
      createField({
        ...payload,
        workflow_scope: payload.workflow_scope ?? workflowScope,
      }),
    onSuccess: invalidate,
  });

  const updateMutation = useMutation({
    mutationFn: ({
      fieldId,
      name,
      coordinates,
    }: {
      fieldId: number;
      name: string;
      coordinates: LonLat[];
    }) => updateField(fieldId, { name, coordinates }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (fieldId: number) => deleteField(fieldId),
    onSuccess: invalidate,
  });

  return {
    fields: query.data ?? [],
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    refresh: invalidate,
    createField: createMutation.mutateAsync,
    updateField: updateMutation.mutateAsync,
    deleteField: deleteMutation.mutateAsync,
    saving: createMutation.isPending || updateMutation.isPending,
    deleting: deleteMutation.isPending,
    workflowScope,
  };
}
