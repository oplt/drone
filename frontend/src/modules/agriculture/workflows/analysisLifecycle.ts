import type { QueryClient } from "@tanstack/react-query";
import type { AgricultureAnalysisRun } from "./analysis/types";
import { agricultureKeys, agriculturePollInterval } from "./queryKeys";

export const AGRICULTURE_RUN_ACTIVE_STATUSES = [
  "queued",
  "orchestrating",
  "waiting_inference",
  "running",
  "processing",
  "pending",
  "waiting",
] as const;

export const AGRICULTURE_RUN_TERMINAL_STATUSES = [
  "completed",
  "succeeded",
  "review_ready",
  "review",
  "published",
  "failed",
  "cancelled",
  "blocked",
  "blocked_quality",
] as const;

export const AGRICULTURE_QUALITY_TERMINAL_STATUSES = [
  "pass",
  "warning",
  "blocked",
  "completed",
  "review",
  "failed",
  "blocked_quality",
] as const;

const activeRunStatuses = new Set<string>(AGRICULTURE_RUN_ACTIVE_STATUSES);
const terminalRunStatuses = new Set<string>(AGRICULTURE_RUN_TERMINAL_STATUSES);
const terminalQualityStatuses = new Set<string>(
  AGRICULTURE_QUALITY_TERMINAL_STATUSES,
);

export function isAgricultureRunTerminal(
  status: string | null | undefined,
): boolean {
  return Boolean(status && terminalRunStatuses.has(status));
}

export function isAgricultureRunActive(
  status: string | null | undefined,
): boolean {
  if (!status) {
    return true;
  }
  if (isAgricultureRunTerminal(status)) {
    return false;
  }
  return activeRunStatuses.has(status) || !terminalRunStatuses.has(status);
}

export function isAgricultureQualityTerminal(
  status: string | null | undefined,
): boolean {
  return Boolean(status && terminalQualityStatuses.has(status));
}

export function agricultureRunPollInterval(
  runStatus: string | null | undefined,
  intervalMs: number,
): number | false {
  return isAgricultureRunActive(runStatus)
    ? agriculturePollInterval(intervalMs)
    : false;
}

export function readAgricultureRunStatus(
  queryClient: QueryClient,
  runId: string | null,
): string | null | undefined {
  if (!runId) {
    return null;
  }
  return queryClient.getQueryData<AgricultureAnalysisRun>(
    agricultureKeys.analysisRun(runId),
  )?.status;
}

export function createAgricultureRunRefetchInterval(
  queryClient: QueryClient,
  runId: string | null,
  intervalMs: number,
): () => number | false {
  return () =>
    agricultureRunPollInterval(
      readAgricultureRunStatus(queryClient, runId),
      intervalMs,
    );
}
