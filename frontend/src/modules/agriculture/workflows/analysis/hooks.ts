import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  assignAgricultureInspectionAction,
  cancelAgricultureAnalysisRun,
  createAgricultureAnalysisRun,
  createAgricultureExport,
  createAgricultureFieldOutcome,
  createAgricultureInspectionPlan,
  createAgriculturePrescription,
  getAgricultureAnalysisLayer,
  getAgricultureAnalysisQuality,
  getAgricultureGrowthStage,
  listAgricultureAnalysisRuns,
  listAgricultureCropRisks,
  listAgricultureExports,
  listAgricultureFieldOutcomes,
  listAgricultureFindings,
  listAgricultureSpatialLayers,
  listAgricultureFusionResults,
  listAgricultureInspectionActions,
  mergeAgricultureFindings,
  processAgricultureCropRisks,
  processAgricultureGrowthStage,
  retryAgricultureAnalysisStage,
  runAgricultureAssistant,
  getAgricultureReport,
  listAgricultureModels,
  getAgricultureModelReleaseGate,
  splitAgricultureFinding,
  updateAgricultureInspectionRoute,
} from "../../api";
import { agricultureKeys, agriculturePollInterval } from "../queryKeys";

export function useAgricultureReport(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.report(runId),
    queryFn: () => getAgricultureReport(runId as string),
    enabled: Boolean(runId),
    staleTime: 15_000,
  });
}

export function useAgricultureAnalysisQuality(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.qualityRun(runId),
    queryFn: () => getAgricultureAnalysisQuality(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      [
        "pass",
        "warning",
        "blocked",
        "completed",
        "review",
        "failed",
        "blocked_quality",
      ].includes(query.state.data?.status ?? "")
        ? false
        : agriculturePollInterval(3000),
  });
}

export function useAgricultureModels(task?: string) {
  return useQuery({ queryKey: agricultureKeys.models(task), queryFn: () => listAgricultureModels(task), staleTime: 30_000 });
}

export function useAgricultureModelReleaseGate(modelId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.models(), "release-gate", modelId], queryFn: () => getAgricultureModelReleaseGate(modelId as string), enabled: Boolean(modelId), staleTime: 10_000 });
}

export function useAgricultureFusionResults(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.fusion(runId),
    queryFn: () => listAgricultureFusionResults(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureCropRisks(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.cropRisks(runId),
    queryFn: () => listAgricultureCropRisks(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureGrowthStage(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.stage(runId),
    queryFn: () => getAgricultureGrowthStage(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureInspectionActions(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.actions(runId),
    queryFn: () => listAgricultureInspectionActions(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureFindings(runId: string | null, limit = 25) {
  return useQuery({
    queryKey: [...agricultureKeys.findings(runId), limit],
    queryFn: () => listAgricultureFindings(runId as string, { limit }),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureFieldOutcomes(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.fieldOutcomes(runId),
    queryFn: () => listAgricultureFieldOutcomes(runId as string),
    enabled: Boolean(runId),
  });
}

export function useMergeAgricultureFindings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: { primary_observation_id: string; member_observation_ids: string[]; reason?: string };
    }) => mergeAgricultureFindings(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.findings(variables.runId) });
      void client.invalidateQueries({ queryKey: agricultureKeys.observations(variables.runId) });
    },
  });
}

export function useSplitAgricultureFinding() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      observationId,
      payload,
    }: {
      runId: string;
      observationId: string;
      payload: { parts: Array<Record<string, unknown>>; reason?: string };
    }) => splitAgricultureFinding(observationId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.findings(variables.runId) });
      void client.invalidateQueries({ queryKey: agricultureKeys.observations(variables.runId) });
    },
  });
}

export function useCreateAgricultureFieldOutcome() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: Parameters<typeof createAgricultureFieldOutcome>[1];
    }) => createAgricultureFieldOutcome(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.fieldOutcomes(variables.runId) });
    },
  });
}

export function useUpdateAgricultureInspectionRoute() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: { ordered_action_ids: string[]; removed_action_ids?: string[]; reason?: string };
    }) => updateAgricultureInspectionRoute(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.actions(variables.runId) });
    },
  });
}

export function useAgricultureExports(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.exports(runId),
    queryFn: () => listAgricultureExports(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useRunAgricultureAssistant() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: { task: string; question: string };
    }) => runAgricultureAssistant(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.assistant(variables.runId),
      });
    },
  });
}

export function useAgricultureLayer(
  runId: string | null,
  layer: string | null,
) {
  return useQuery({
    queryKey: [...agricultureKeys.all, "layer", runId, layer],
    queryFn: () =>
      getAgricultureAnalysisLayer(runId as string, layer as string),
    enabled: Boolean(runId && layer),
    staleTime: 15_000,
  });
}

export function useAgricultureSpatialLayers(runId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.all, "spatial-layers", runId], queryFn: () => listAgricultureSpatialLayers(runId as string), enabled: Boolean(runId), staleTime: 15_000 });
}

export function useCreateAgricultureAnalysisRun() {
  return useMutation({ mutationFn: createAgricultureAnalysisRun });
}

export function useAgricultureAnalysisRuns(flightId: string | null) {
  return useQuery({
    queryKey: [...agricultureKeys.flight(flightId), "analysis-runs"],
    queryFn: () => listAgricultureAnalysisRuns(flightId as string),
    enabled: Boolean(flightId),
    staleTime: 5000,
  });
}

export function useCancelAgricultureAnalysisRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: cancelAgricultureAnalysisRun,
    onSuccess: (run) => {
      void client.invalidateQueries({
        queryKey: [...agricultureKeys.flight(run.flight_id), "analysis-runs"],
      });
      void client.invalidateQueries({
        queryKey: agricultureKeys.analysisRun(run.id),
      });
    },
  });
}

export function useRetryAgricultureAnalysisStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, stageName, reason }: { runId: string; stageName: string; reason?: string }) => retryAgricultureAnalysisStage(runId, stageName, reason),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.qualityRun(result.run_id) });
      void client.invalidateQueries({ queryKey: agricultureKeys.analysisRun(result.run_id) });
    },
  });
}

export function useProcessAgricultureCropRisks() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureCropRisks(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.cropRisks(variables.runId),
      });
    },
  });
}

export function useProcessAgricultureGrowthStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureGrowthStage(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.stage(variables.runId),
      });
    },
  });
}

export function useCreateAgricultureInspectionPlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => createAgricultureInspectionPlan(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.actions(variables.runId),
      });
    },
  });
}

export function useAssignAgricultureInspectionAction() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (variables: { id: string; runId: string; payload: Parameters<typeof assignAgricultureInspectionAction>[1] }) => assignAgricultureInspectionAction(variables.id, variables.payload), onSuccess: (_result, variables) => { void client.invalidateQueries({ queryKey: agricultureKeys.actions(variables.runId) }); } });
}

export function useCreateAgriculturePrescription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, ruleId }: { runId: string; ruleId: string }) =>
      createAgriculturePrescription(runId, ruleId),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.prescriptions(variables.runId),
      });
    },
  });
}

export function useCreateAgricultureExport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: { artifact_kind: string; format: string; source_id?: string };
    }) => createAgricultureExport(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.exports(variables.runId),
      });
    },
  });
}
