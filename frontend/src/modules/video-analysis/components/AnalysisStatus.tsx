import { Alert, Button, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import type { VideoAnalysisJob, VideoAsset, VideoDetection } from "../types";

export type AnalysisStatusProps = {
  job?: VideoAnalysisJob;
  detectionCount: number;
  cancelling?: boolean;
  onCancel?: () => void;
  video?: VideoAsset | null;
  detections?: VideoDetection[];
};

function hasLowConfidenceGeoref(detections: VideoDetection[] | undefined): boolean {
  return (detections ?? []).some((detection) => {
    const quality = detection.telemetry_match_quality ?? "";
    return (
      quality === "low_confidence" ||
      quality === "low_confidence_upload_time" ||
      quality.includes("low_confidence")
    );
  });
}

export function AnalysisResultsSection({
  job,
  detectionCount,
  cancelling,
  onCancel,
  video,
  detections,
}: AnalysisStatusProps) {
  const progress = Math.min(100, Math.max(0, job?.progress ?? 0));
  const color = job?.status === "failed" ? "error" : job?.status === "completed" ? "success" : "info";
  const completedWithoutMatches = job?.status === "completed" && detectionCount === 0;
  const uploadTimeFallback =
    video?.capture_time_source === "upload_time" ||
    (detections ?? []).some((detection) => detection.capture_time_source === "upload_time");
  const lowConfidenceMatch = hasLowConfidenceGeoref(detections);
  const failureGuidance: Record<string, string> = {
    QUEUE_UNAVAILABLE: "The analysis worker was unavailable. Wait briefly, then run analysis again.",
    WORKER_LEASE_EXPIRED: "The worker stopped reporting progress. Run analysis again to create a fresh attempt.",
    NO_SUCCESSFUL_FRAMES: "No sampled frame completed inference. Check that the recording decodes, then retry or choose another model.",
    INFERENCE_FAILED: "Inference failed. Review the model and sampling settings, then run analysis again.",
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h6">Processing status</Typography>
        <Chip size="small" color={color} label={job?.status ?? "Not started"} />
      </Stack>
      <LinearProgress color={color} variant="determinate" value={progress} />
      <Typography variant="body2" color="text.secondary">
        {job
          ? `${progress.toFixed(1)}% processed | ${detectionCount} detections received`
          : "Run analysis to populate review layers."}
      </Typography>
      {video?.reanalysis_required ? (
        <Alert severity="warning">
          Capture time or sync offset changed after a prior analysis. Run analysis again so
          georeferencing uses the corrected metadata. Existing detection provenance is unchanged.
        </Alert>
      ) : null}
      {uploadTimeFallback ? (
        <Alert severity="warning">
          Capture time fell back to upload time. Map locations may be inaccurate until an operator
          sets the true capture time or sync offset.
        </Alert>
      ) : null}
      {lowConfidenceMatch ? (
        <Alert severity="warning">
          Some detections have low-confidence telemetry matches. Treat map positions as approximate.
        </Alert>
      ) : null}
      {job?.status === "queued" ? (
        <Alert severity="info">Waiting for an analysis worker to start this job.</Alert>
      ) : null}
      {job?.status === "running" && detectionCount === 0 ? (
        <Alert severity="info">
          Analyzing sampled frames. Detections appear when objects match the selected model and
          confidence.
        </Alert>
      ) : null}
      {job && ["queued", "running"].includes(job.status) && onCancel ? (
        <Button size="small" color="warning" disabled={cancelling} onClick={onCancel}>
          {cancelling ? "Cancelling…" : "Cancel analysis"}
        </Button>
      ) : null}
      {completedWithoutMatches ? (
        <Alert severity="warning">
          Analysis completed, but no objects matched. Try a lower confidence threshold or another
          model.
        </Alert>
      ) : null}
      {job?.status === "failed" ? (
        <Alert severity="error">
          {job.terminal_stage ? `Failed during ${job.terminal_stage.replaceAll("_", " ")}. ` : ""}
          {job.error ?? "Analysis failed."}{" "}
          {failureGuidance[job.terminal_reason_code ?? ""] ?? "Adjust the inference settings and run analysis again."}
        </Alert>
      ) : null}
    </Stack>
  );
}

export function AnalysisStatus(props: AnalysisStatusProps) {
  return <AnalysisResultsSection {...props} />;
}
