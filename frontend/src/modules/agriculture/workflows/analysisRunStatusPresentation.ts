import {
  isAgricultureRunActive,
  isAgricultureRunTerminal,
} from "./analysisLifecycle";

export type AnalysisRunChipColor =
  | "default"
  | "error"
  | "info"
  | "success"
  | "warning";

export type AnalysisStagePresentation = {
  key: string;
  name: string;
  rawStatus: string;
  label: string;
  chipColor: AnalysisRunChipColor;
  progressPercent: number;
  error?: string;
  deadLetter: boolean;
  retryable: boolean;
};

export type AnalysisRunStatusPresentation = {
  rawStatus: string;
  label: string;
  chipColor: AnalysisRunChipColor;
  progressPercent: number;
  summaryLine: string;
  isActive: boolean;
  isTerminal: boolean;
  isCancelling: boolean;
  isCancelled: boolean;
  isReplayable: boolean;
  hasRetryableStages: boolean;
  qualityBlocked: boolean;
  qualityBlockReason?: string;
  currentStage?: AnalysisStagePresentation;
  currentStageLabel?: string;
  lastUpdatedAt?: string;
  lastUpdatedLabel?: string;
  retryCount: number;
};

export type AnalysisRunStatusInput = {
  status: string;
  progress?: number;
  error?: string | null;
  stages?: Array<Record<string, unknown>>;
  qualityGate?: Record<string, unknown> | null;
  retryCount?: number;
  createdAt?: string | null;
  updatedAt?: string | null;
};

const REPLAYABLE_RUN_STATUSES = new Set([
  "failed",
  "cancelled",
  "blocked_quality",
]);

const ACTIVE_STAGE_STATUSES = new Set([
  "running",
  "queued",
  "waiting",
  "waiting_inference",
  "orchestrating",
  "processing",
  "pending",
]);

const RUN_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  orchestrating: "Orchestrating",
  waiting_inference: "Waiting for inference",
  waiting: "Waiting",
  running: "Running",
  processing: "Processing",
  pending: "Pending",
  cancelling: "Cancelling",
  cancelled: "Cancelled",
  completed: "Completed",
  succeeded: "Succeeded",
  review_ready: "Ready for review",
  review: "In review",
  published: "Published",
  failed: "Failed",
  blocked: "Blocked",
  blocked_quality: "Blocked by quality gate",
};

const RUN_STATUS_CHIP_COLORS: Record<string, AnalysisRunChipColor> = {
  queued: "info",
  orchestrating: "info",
  waiting_inference: "warning",
  waiting: "warning",
  running: "info",
  processing: "info",
  pending: "info",
  cancelling: "warning",
  cancelled: "default",
  completed: "success",
  succeeded: "success",
  review_ready: "success",
  review: "success",
  published: "success",
  failed: "error",
  blocked: "error",
  blocked_quality: "error",
};

const STAGE_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  dead_letter: "Dead letter",
  waiting: "Waiting",
  waiting_inference: "Waiting for inference",
};

const STAGE_STATUS_CHIP_COLORS: Record<string, AnalysisRunChipColor> = {
  queued: "default",
  running: "info",
  completed: "success",
  failed: "error",
  dead_letter: "error",
  waiting: "warning",
  waiting_inference: "warning",
};

const QUALITY_STATUS_LABELS: Record<string, string> = {
  pass: "Pass",
  warning: "Warning",
  blocked: "Blocked",
  not_applicable: "Not applicable",
  not_measured: "Not measured",
};

const QUALITY_STATUS_CHIP_COLORS: Record<string, AnalysisRunChipColor> = {
  pass: "success",
  warning: "warning",
  blocked: "error",
  not_applicable: "default",
  not_measured: "default",
};

export function normalizeAnalysisRunStatus(
  status: string | null | undefined,
): string {
  return String(status ?? "unknown")
    .trim()
    .toLowerCase();
}

export function formatAnalysisRunProgress(
  progress: number | null | undefined,
): number {
  const value = Number(progress ?? 0);
  if (!Number.isFinite(value)) {
    return 0;
  }
  const percent = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, percent));
}

export function formatAnalysisStageName(stageName: string | null | undefined): string {
  return String(stageName ?? "stage").replaceAll("_", " ");
}

export function formatAnalysisStatusLabel(
  status: string | null | undefined,
): string {
  const normalized = normalizeAnalysisRunStatus(status);
  if (RUN_STATUS_LABELS[normalized]) {
    return RUN_STATUS_LABELS[normalized];
  }
  if (!normalized || normalized === "unknown") {
    return "Unknown";
  }
  return formatAnalysisStageName(normalized);
}

export function analysisRunStatusChipColor(
  status: string | null | undefined,
): AnalysisRunChipColor {
  return RUN_STATUS_CHIP_COLORS[normalizeAnalysisRunStatus(status)] ?? "default";
}

export function isAnalysisRunReplayable(
  status: string | null | undefined,
): boolean {
  return REPLAYABLE_RUN_STATUSES.has(normalizeAnalysisRunStatus(status));
}

export function isAnalysisStageRetryable(
  stage: Record<string, unknown>,
): boolean {
  const status = normalizeAnalysisRunStatus(String(stage.status ?? "queued"));
  if (stage.dead_letter) {
    return stage.retryable !== false;
  }
  return (
    (status === "failed" || status === "dead_letter") &&
    stage.retryable !== false
  );
}

function formatStageStatusLabel(status: string): string {
  const normalized = normalizeAnalysisRunStatus(status);
  if (STAGE_STATUS_LABELS[normalized]) {
    return STAGE_STATUS_LABELS[normalized];
  }
  return formatAnalysisStatusLabel(status);
}

function stageStatusChipColor(status: string): AnalysisRunChipColor {
  return (
    STAGE_STATUS_CHIP_COLORS[normalizeAnalysisRunStatus(status)] ?? "default"
  );
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => String(item).trim())
    .filter(Boolean);
}

function formatReasonList(reasons: string[]): string | undefined {
  if (!reasons.length) {
    return undefined;
  }
  return reasons.map((reason) => formatAnalysisStageName(reason)).join(", ");
}

export function extractQualityBlockReason(input: {
  status?: string | null;
  error?: string | null;
  qualityGate?: Record<string, unknown> | null;
}): string | undefined {
  const normalizedStatus = normalizeAnalysisRunStatus(input.status);
  const qualityGate = input.qualityGate ?? {};
  const gateStatus = normalizeAnalysisRunStatus(String(qualityGate.status ?? ""));
  const blocked =
    normalizedStatus === "blocked_quality" ||
    normalizedStatus === "blocked" ||
    gateStatus === "blocked";

  if (!blocked) {
    return undefined;
  }

  const gateReasons = formatReasonList(readStringList(qualityGate.reasons));
  if (gateReasons) {
    return gateReasons;
  }

  const message = String(qualityGate.message ?? "").trim();
  if (message) {
    return message;
  }

  const runError = String(input.error ?? "").trim();
  if (runError) {
    return runError;
  }

  return "Quality gate blocked agricultural inference";
}

export function buildQualityGatePresentation(input: {
  qualityGate?: Record<string, unknown> | null;
  fallbackStatus?: string | null;
}): {
  label: string;
  chipColor: AnalysisRunChipColor;
  blocked: boolean;
  reason?: string;
} {
  const qualityGate = input.qualityGate ?? {};
  const status = normalizeAnalysisRunStatus(
    String(qualityGate.status ?? input.fallbackStatus ?? "unknown"),
  );
  const label = QUALITY_STATUS_LABELS[status] ?? formatAnalysisStatusLabel(status);
  const chipColor = QUALITY_STATUS_CHIP_COLORS[status] ?? "default";
  const blocked = status === "blocked" || status === "blocked_quality";
  const reason = blocked
    ? extractQualityBlockReason({
        status,
        qualityGate,
      })
    : undefined;

  return { label, chipColor, blocked, reason };
}

function resolveLastUpdatedAt(input: AnalysisRunStatusInput): string | undefined {
  const candidates: string[] = [];
  const push = (value: unknown) => {
    if (typeof value === "string" && value.trim()) {
      candidates.push(value);
    }
  };

  push(input.updatedAt);
  for (const stage of input.stages ?? []) {
    push(stage.finished_at);
    push(stage.started_at);
    push(stage.last_error_at);
    push(stage.dead_letter_at);
  }
  push(input.createdAt);

  if (!candidates.length) {
    return undefined;
  }

  return candidates.sort(
    (left, right) => new Date(right).getTime() - new Date(left).getTime(),
  )[0];
}

function buildStagePresentation(
  stage: Record<string, unknown>,
): AnalysisStagePresentation {
  const rawStatus = normalizeAnalysisRunStatus(String(stage.status ?? "queued"));
  const progressPercent = formatAnalysisRunProgress(Number(stage.progress ?? 0));
  const label = formatStageStatusLabel(rawStatus);
  const deadLetter = Boolean(stage.dead_letter);
  const displayStatus = deadLetter ? "dead letter" : rawStatus;

  return {
    key: String(stage.id ?? stage.stage_name ?? displayStatus),
    name: formatAnalysisStageName(String(stage.stage_name ?? "stage")),
    rawStatus,
    label,
    chipColor: deadLetter ? "error" : stageStatusChipColor(rawStatus),
    progressPercent,
    error: stage.error ? String(stage.error) : undefined,
    deadLetter,
    retryable: isAnalysisStageRetryable(stage),
  };
}

function findCurrentStage(
  stages: Array<Record<string, unknown>>,
): AnalysisStagePresentation | undefined {
  for (const stage of stages) {
    const rawStatus = normalizeAnalysisRunStatus(String(stage.status ?? "queued"));
    if (
      ACTIVE_STAGE_STATUSES.has(rawStatus) ||
      rawStatus === "failed" ||
      stage.dead_letter
    ) {
      return buildStagePresentation(stage);
    }
  }

  if (!stages.length) {
    return undefined;
  }

  return buildStagePresentation(stages[stages.length - 1]!);
}

export function buildAnalysisStagePresentations(
  stages: Array<Record<string, unknown>> | undefined,
): AnalysisStagePresentation[] {
  return (stages ?? []).map((stage) => buildStagePresentation(stage));
}

export function buildAnalysisRunStatusPresentation(
  input: AnalysisRunStatusInput,
): AnalysisRunStatusPresentation {
  const rawStatus = normalizeAnalysisRunStatus(input.status);
  const label = formatAnalysisStatusLabel(rawStatus);
  const chipColor = analysisRunStatusChipColor(rawStatus);
  const progressPercent = formatAnalysisRunProgress(input.progress);
  const stages = input.stages ?? [];
  const stagePresentations = buildAnalysisStagePresentations(stages);
  const currentStage = findCurrentStage(stages);
  const qualityBlocked =
    rawStatus === "blocked_quality" ||
    rawStatus === "blocked" ||
    normalizeAnalysisRunStatus(String(input.qualityGate?.status ?? "")) ===
      "blocked";
  const qualityBlockReason = extractQualityBlockReason({
    status: rawStatus,
    error: input.error,
    qualityGate: input.qualityGate,
  });
  const lastUpdatedAt = resolveLastUpdatedAt(input);
  const lastUpdatedLabel = lastUpdatedAt
    ? new Date(lastUpdatedAt).toLocaleString()
    : undefined;
  const isCancelling = rawStatus === "cancelling";
  const isCancelled = rawStatus === "cancelled";
  const retryCount = Number(input.retryCount ?? 0);
  const hasRetryableStages = stagePresentations.some((stage) => stage.retryable);

  return {
    rawStatus,
    label,
    chipColor,
    progressPercent,
    summaryLine: `${label} · ${Math.round(progressPercent)}%`,
    isActive: isAgricultureRunActive(rawStatus),
    isTerminal: isAgricultureRunTerminal(rawStatus),
    isCancelling,
    isCancelled,
    isReplayable: isAnalysisRunReplayable(rawStatus),
    hasRetryableStages,
    qualityBlocked,
    qualityBlockReason,
    currentStage,
    currentStageLabel: currentStage?.name,
    lastUpdatedAt,
    lastUpdatedLabel,
    retryCount,
  };
}
