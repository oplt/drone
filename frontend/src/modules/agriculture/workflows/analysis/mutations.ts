import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveAgricultureAssistantRun,
  approveAgricultureInspectionAction,
  approveAgriculturePrescription,
  correctAgricultureGrowthStage,
  getAgricultureSpatialViewport,
  getAgricultureAnalysisRun,
  getAgricultureExportDownload,
  getAgricultureYieldForecast,
  listAgricultureAssistantRuns,
  listAgricultureGrowthMetrics,
  listAgriculturePrescriptions,
  processAgricultureAnalysisRun,
  processAgricultureFusion,
  processAgricultureGrowthMetric,
  processAgricultureYieldForecast,
  replayAgricultureAnalysisRun,
  createAgricultureReportSnapshot,
  listAgricultureReportSnapshots,
  listAgricultureModelQualityReports,
  runAgricultureModelShadowEvaluation,
  publishAgricultureModel,
  rollbackAgricultureModel,
  monitorAgricultureModelDrift,
  getAgricultureAnalysisReadiness,
} from "../../api";
import { agricultureKeys, agriculturePollInterval } from "../queryKeys";

export function useAgricultureReportSnapshots(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.reportSnapshots(runId),
    queryFn: () => listAgricultureReportSnapshots(runId as string),
    enabled: Boolean(runId),
  });
}

export function useCreateAgricultureReportSnapshot() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, templateKey, comparisonId }: { runId: string; templateKey?: "standard" | "executive" | "field_visit" | "decision"; comparisonId?: string }) =>
      createAgricultureReportSnapshot(runId, templateKey, comparisonId),
    onSuccess: (_snapshot, variables) => {
      void client.invalidateQueries({ queryKey: agricultureKeys.reportSnapshots(variables.runId) });
    },
  });
}

export function useAgricultureAnalysisRun(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.analysisRun(runId),
    queryFn: () => getAgricultureAnalysisRun(runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      ["completed", "failed", "blocked", "review"].includes(
        query.state.data?.status ?? "",
      )
        ? false
        : agriculturePollInterval(3000),
  });
}

export function useAgricultureModelQualityReports(modelId: string | null) {
  return useQuery({ queryKey: [...agricultureKeys.models(), "quality", modelId], queryFn: () => listAgricultureModelQualityReports(modelId as string), enabled: Boolean(modelId), staleTime: 30_000 });
}

export function useAgricultureModelGovernanceActions() {
  const client = useQueryClient();
  const invalidate = () => { void client.invalidateQueries({ queryKey: agricultureKeys.models() }); };
  return {
    shadow: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof runAgricultureModelShadowEvaluation>[1] }) => runAgricultureModelShadowEvaluation(id, payload), onSuccess: invalidate }),
    publish: useMutation({ mutationFn: publishAgricultureModel, onSuccess: invalidate }),
    rollback: useMutation({ mutationFn: ({ id, targetId }: { id: string; targetId: string }) => rollbackAgricultureModel(id, targetId), onSuccess: invalidate }),
    drift: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof monitorAgricultureModelDrift>[1] }) => monitorAgricultureModelDrift(id, payload), onSuccess: invalidate }),
  };
}

export function useAgricultureGrowthMetrics(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.growth(runId),
    queryFn: () => listAgricultureGrowthMetrics(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureYieldForecast(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.yield(runId),
    queryFn: () => getAgricultureYieldForecast(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgriculturePrescriptions(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.prescriptions(runId),
    queryFn: () => listAgriculturePrescriptions(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useAgricultureAssistantRuns(runId: string | null) {
  return useQuery({
    queryKey: agricultureKeys.assistant(runId),
    queryFn: () => listAgricultureAssistantRuns(runId as string),
    enabled: Boolean(runId),
    refetchInterval: () => agriculturePollInterval(5000),
  });
}

export function useApproveAgricultureAssistantRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
      note,
    }: {
      id: string;
      runId: string;
      status: "approved" | "rejected";
      note?: string;
    }) => approveAgricultureAssistantRun(id, status, note),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.assistant(variables.runId),
      });
    },
  });
}

export function useAgricultureSpatialViewport(runId: string | null, options: { layer?: string; zoom?: number; minSeverity?: number; minConfidence?: number } = {}) {
  const layer = options.layer ?? "all";
  const zoom = options.zoom ?? 12;
  const minConfidence = options.minConfidence ?? 0;
  return useQuery({
    queryKey: agricultureKeys.spatial(runId, layer, zoom, minConfidence),
    queryFn: () => getAgricultureSpatialViewport(runId as string, { ...options, layer, zoom, minConfidence }),
    enabled: Boolean(runId),
    staleTime: 15_000,
  });
}

export function useAgricultureAnalysisReadiness(flightId: string | null, enabled = true) {
  return useQuery({
    queryKey: agricultureKeys.analysisReadiness(flightId),
    queryFn: () => getAgricultureAnalysisReadiness(flightId as string),
    enabled: Boolean(flightId && enabled),
    staleTime: 10_000,
  });
}

export function useProcessAgricultureAnalysisRun() {
  return useMutation({ mutationFn: processAgricultureAnalysisRun });
}

export function useReplayAgricultureAnalysisRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: replayAgricultureAnalysisRun,
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

export function useProcessAgricultureFusion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureFusion(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.fusion(variables.runId),
      });
    },
  });
}

export function useProcessAgricultureGrowthMetric() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload: Record<string, unknown>;
    }) => processAgricultureGrowthMetric(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.growth(variables.runId),
      });
    },
  });
}

export function useCorrectAgricultureGrowthStage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      estimateId,
      payload,
    }: {
      estimateId: string;
      payload: { human_stage: string; note?: string };
    }) => correctAgricultureGrowthStage(estimateId, payload),
    onSuccess: (result) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.stage(result.run_id),
      });
    },
  });
}

export function useApproveAgricultureInspectionAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      runId: string;
      status: "approved" | "rejected";
    }) => approveAgricultureInspectionAction(id, status),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.actions(variables.runId),
      });
    },
  });
}

export function useApproveAgriculturePrescription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      runId: string;
      status: "approved" | "rejected";
    }) => approveAgriculturePrescription(id, status),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.prescriptions(variables.runId),
      });
    },
  });
}

export function useGetAgricultureExportDownload() {
  return useMutation({ mutationFn: getAgricultureExportDownload });
}

export function useProcessAgricultureYieldForecast() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      payload,
    }: {
      runId: string;
      payload?: Record<string, unknown>;
    }) => processAgricultureYieldForecast(runId, payload),
    onSuccess: (_result, variables) => {
      void client.invalidateQueries({
        queryKey: agricultureKeys.yield(variables.runId),
      });
    },
  });
}
