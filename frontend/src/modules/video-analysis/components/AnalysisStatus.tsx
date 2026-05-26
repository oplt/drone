import { Alert, Card, CardContent, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import type { VideoAnalysisJob } from "../types";

type Props = { job?: VideoAnalysisJob; detectionCount: number };

export function AnalysisStatus({ job, detectionCount }: Props) {
  const progress = Math.min(100, Math.max(0, job?.progress ?? 0));
  const color = job?.status === "failed" ? "error" : job?.status === "completed" ? "success" : "info";
  const completedWithoutMatches = job?.status === "completed" && detectionCount === 0;
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Typography variant="overline" color="text.secondary">03 / Results</Typography>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">Processing status</Typography>
            <Chip size="small" color={color} label={job?.status ?? "Not started"} />
          </Stack>
          <LinearProgress color={color} variant="determinate" value={progress} />
          <Typography variant="body2" color="text.secondary">
            {job ? `${progress.toFixed(1)}% processed | ${detectionCount} detections received` : "Run analysis to populate review layers."}
          </Typography>
          {job?.status === "queued" ? <Alert severity="info">Waiting for an analysis worker to start this job.</Alert> : null}
          {job?.status === "running" && detectionCount === 0 ? <Alert severity="info">Analyzing sampled frames. Detections appear when objects match the selected model and confidence.</Alert> : null}
          {completedWithoutMatches ? <Alert severity="warning">Analysis completed, but no objects matched. Try a lower confidence threshold or another model.</Alert> : null}
          {job?.status === "failed" ? <Alert severity="error">{job.error ?? "Analysis failed."}</Alert> : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
