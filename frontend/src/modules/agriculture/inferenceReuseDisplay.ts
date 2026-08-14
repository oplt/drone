import type { InferenceReuseSummary } from "./workflows/analysis/types";

export function hasReusedInference(
  reuse: InferenceReuseSummary | null | undefined,
): reuse is InferenceReuseSummary {
  return Boolean(reuse && reuse.reused_job_count > 0);
}

export function formatInferenceReuseHeadline(
  reuse: InferenceReuseSummary,
): string {
  if (reuse.fully_reused) {
    return "Validated video inference reused for all sources in this run.";
  }
  return `Validated video inference reused for ${reuse.reused_job_count} of ${reuse.total_job_count} sources.`;
}

export function formatCompletedAt(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString();
}

export function summarizeReuseDetail(
  reuse: InferenceReuseSummary,
): string[] {
  const detail = reuse.details.find((item) => item.reused) ?? reuse.details[0];
  if (!detail) return [];
  const lines: string[] = [];
  if (detail.source_checksum) {
    lines.push(`Source checksum: ${detail.source_checksum.slice(0, 12)}…`);
  }
  if (detail.model_checksum || detail.vision_model_version_id) {
    lines.push(
      `Model match: ${detail.vision_model_version_id ?? "version"} · ${(detail.model_checksum ?? "checksum").slice(0, 12)}…`,
    );
  }
  if (Object.keys(detail.inference_profile).length > 0) {
    lines.push("Inference profile matches the validated prior run.");
  }
  if (detail.reused_from_run_id) {
    lines.push(`Prior run: ${detail.reused_from_run_id}`);
  }
  const completedAt = formatCompletedAt(detail.original_completed_at);
  if (completedAt) {
    lines.push(`Originally completed: ${completedAt}`);
  }
  if (reuse.run_input_checksum) {
    lines.push(`Run input checksum: ${reuse.run_input_checksum.slice(0, 12)}…`);
  }
  return lines;
}
