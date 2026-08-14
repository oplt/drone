import type { VisionTrainingRun } from "./visionTypes";

export type VisionTrainingChipColor =
  | "default"
  | "error"
  | "info"
  | "success"
  | "warning";

export type VisionTrainingRunListPresentation = {
  id: string;
  modelLabel: string;
  presetLabel: string;
  statusLabel: string;
  chipColor: VisionTrainingChipColor;
  epochLabel: string;
  progressPercent: number;
  device: string;
  isActive: boolean;
  isRetryable: boolean;
  isCancellable: boolean;
  hasEvaluation: boolean;
};

export type VisionTrainingRunDetailMetrics = {
  trainLoss: number | null;
  valLoss: number | null;
  precision: number | null;
  recall: number | null;
  map50: number | null;
  map50_95: number | null;
  epochDurationSeconds: number | null;
  gpuUtilization: number | null;
  bestEpoch: number | null;
  checkpointStatus: string;
  evaluationStatus: string;
};

const ACTIVE_STATUSES = new Set(["queued", "running", "cancelling"]);
const RETRYABLE_STATUSES = new Set(["failed", "cancelled"]);
const CANCELLABLE_STATUSES = new Set(["queued", "running"]);

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  cancelling: "Cancelling",
  cancelled: "Cancelled",
  completed: "Completed",
  failed: "Failed",
};

const STATUS_CHIP_COLORS: Record<string, VisionTrainingChipColor> = {
  queued: "info",
  running: "info",
  cancelling: "warning",
  cancelled: "default",
  completed: "success",
  failed: "error",
};

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function firstNumber(
  records: Array<Record<string, unknown> | null | undefined>,
  keys: string[],
): number | null {
  for (const record of records) {
    if (!record) {
      continue;
    }
    for (const key of keys) {
      const value = asNumber(record[key]);
      if (value != null) {
        return value;
      }
    }
  }
  return null;
}

export function normalizeVisionTrainingStatus(
  status: string | null | undefined,
): string {
  return String(status ?? "unknown").trim().toLowerCase();
}

export function formatVisionTrainingStatusLabel(
  status: string | null | undefined,
): string {
  const normalized = normalizeVisionTrainingStatus(status);
  return STATUS_LABELS[normalized] ?? normalized.replaceAll("_", " ");
}

export function visionTrainingStatusChipColor(
  status: string | null | undefined,
): VisionTrainingChipColor {
  return STATUS_CHIP_COLORS[normalizeVisionTrainingStatus(status)] ?? "default";
}

export function formatVisionTrainingPresetLabel(preset: string): string {
  return preset
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatVisionTrainingProgress(
  progress: number | null | undefined,
): number {
  const value = Number(progress ?? 0);
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function estimateEpochDurationSeconds(run: VisionTrainingRun): number | null {
  if (!run.started_at || run.current_epoch <= 0) {
    return null;
  }
  const endMs = new Date(run.finished_at ?? Date.now()).getTime();
  const startMs = new Date(run.started_at).getTime();
  const elapsedSeconds = (endMs - startMs) / 1000;
  if (elapsedSeconds <= 0) {
    return null;
  }
  return elapsedSeconds / run.current_epoch;
}

function resolveBestEpoch(run: VisionTrainingRun): number | null {
  const training = (run.metrics.training ?? {}) as Record<string, unknown>;
  return (
    asNumber(training.best_epoch) ??
    asNumber(training["best/epoch"]) ??
    (run.status === "completed" ? run.current_epoch : null)
  );
}

function resolveGpuUtilization(run: VisionTrainingRun): number | null {
  const training = (run.metrics.training ?? {}) as Record<string, unknown>;
  return (
    asNumber(training.gpu_utilization) ??
    asNumber(training["gpu/utilization"]) ??
    asNumber(training.gpu_util)
  );
}

function resolveCheckpointStatus(run: VisionTrainingRun): string {
  if (run.status === "completed") {
    return run.model_version_id ? "Checkpoint published" : "Checkpoint missing";
  }
  if (run.status === "running") {
    return "Training in progress";
  }
  if (run.status === "queued") {
    return "Queued";
  }
  if (run.status === "cancelling") {
    return "Cancellation requested";
  }
  if (run.status === "cancelled") {
    return "Cancelled before publish";
  }
  return "Checkpoint unavailable";
}

function resolveEvaluationStatus(run: VisionTrainingRun): string {
  if (run.model_version_id) {
    return "Evaluation completed";
  }
  if (run.status === "failed") {
    return "Evaluation failed";
  }
  if (ACTIVE_STATUSES.has(run.status)) {
    return "Evaluation pending";
  }
  if (run.status === "cancelled") {
    return "Evaluation skipped";
  }
  return "Evaluation unavailable";
}

export function extractVisionTrainingRunMetrics(
  run: VisionTrainingRun,
): VisionTrainingRunDetailMetrics {
  const summary = (run.metrics.summary ?? {}) as Record<string, unknown>;
  const training = (run.metrics.training ?? {}) as Record<string, unknown>;
  const records = [summary, training, run.metrics];

  return {
    trainLoss: firstNumber(records, ["train/box_loss", "train/loss", "box_loss"]),
    valLoss: firstNumber(records, ["val/box_loss", "val/loss"]),
    precision: firstNumber(records, [
      "precision",
      "metrics/precision(B)",
    ]),
    recall: firstNumber(records, ["recall", "metrics/recall(B)"]),
    map50: firstNumber(records, ["map50", "metrics/mAP50(B)"]),
    map50_95: firstNumber(records, [
      "map50_95",
      "metrics/mAP50-95(B)",
    ]),
    epochDurationSeconds: estimateEpochDurationSeconds(run),
    gpuUtilization: resolveGpuUtilization(run),
    bestEpoch: resolveBestEpoch(run),
    checkpointStatus: resolveCheckpointStatus(run),
    evaluationStatus: resolveEvaluationStatus(run),
  };
}

export function buildVisionTrainingRunListPresentation(
  run: VisionTrainingRun,
): VisionTrainingRunListPresentation {
  const normalizedStatus = normalizeVisionTrainingStatus(run.status);
  return {
    id: run.id,
    modelLabel: run.base_model,
    presetLabel: formatVisionTrainingPresetLabel(run.preset),
    statusLabel: formatVisionTrainingStatusLabel(run.status),
    chipColor: visionTrainingStatusChipColor(run.status),
    epochLabel: `${run.current_epoch}/${run.total_epochs}`,
    progressPercent: formatVisionTrainingProgress(run.progress),
    device: run.device,
    isActive: ACTIVE_STATUSES.has(normalizedStatus),
    isRetryable: RETRYABLE_STATUSES.has(normalizedStatus),
    isCancellable: CANCELLABLE_STATUSES.has(normalizedStatus),
    hasEvaluation: Boolean(run.model_version_id),
  };
}

export function formatTrainingMetricNumber(
  value: number | null | undefined,
  digits = 4,
): string {
  if (value == null) {
    return "—";
  }
  return value.toFixed(digits);
}

export function formatTrainingDurationSeconds(
  value: number | null | undefined,
): string {
  if (value == null) {
    return "—";
  }
  if (value < 60) {
    return `${value.toFixed(1)} s`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes}m ${seconds}s`;
}

export function formatGpuUtilization(
  value: number | null | undefined,
): string {
  if (value == null) {
    return "—";
  }
  const percent = value <= 1 ? value * 100 : value;
  return `${percent.toFixed(0)}%`;
}
