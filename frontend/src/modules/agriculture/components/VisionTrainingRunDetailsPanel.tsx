import { RocketLaunch } from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { percent } from "../evaluationDisplay";
import type { VisionTrainingRun } from "../visionTypes";
import {
  buildVisionTrainingRunListPresentation,
  extractVisionTrainingRunMetrics,
  formatGpuUtilization,
  formatTrainingDurationSeconds,
  formatTrainingMetricNumber,
} from "../trainingRunPresentation";

function MetricTile({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description?: string;
}) {
  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h5">{value}</Typography>
        {description ? (
          <Typography variant="caption" color="text.secondary">
            {description}
          </Typography>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function VisionTrainingRunDetailsPanel({
  run,
  onCancel,
  cancelPending,
  onRetry,
  retryDisabled,
  retryPending,
  onOpenEvaluation,
}: {
  run: VisionTrainingRun;
  onCancel?: () => void;
  cancelPending?: boolean;
  onRetry?: () => void;
  retryDisabled?: boolean;
  retryPending?: boolean;
  onOpenEvaluation?: () => void;
}) {
  const presentation = buildVisionTrainingRunListPresentation(run);
  const metrics = extractVisionTrainingRunMetrics(run);

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        spacing={2}
      >
        <Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="h5">
              {presentation.modelLabel} · {presentation.presetLabel}
            </Typography>
            <Chip
              size="small"
              label={presentation.statusLabel}
              color={presentation.chipColor}
            />
            {presentation.hasEvaluation ? (
              <Chip
                size="small"
                icon={<RocketLaunch />}
                label="Evaluation completed"
                color="success"
                variant="outlined"
              />
            ) : null}
          </Stack>
          <Typography color="text.secondary">
            Epoch {presentation.epochLabel} · {presentation.device} · Trainer{" "}
            {run.trainer}
          </Typography>
          {run.started_at ? (
            <Typography variant="caption" color="text.secondary">
              Started {new Date(run.started_at).toLocaleString()}
              {run.finished_at
                ? ` · Finished ${new Date(run.finished_at).toLocaleString()}`
                : ""}
            </Typography>
          ) : null}
        </Box>
        <Stack direction="row" spacing={1} alignItems="flex-start">
          {presentation.isCancellable && onCancel ? (
            <Button color="warning" disabled={cancelPending} onClick={onCancel}>
              {cancelPending ? "Cancelling…" : "Cancel run"}
            </Button>
          ) : null}
          {presentation.isRetryable && onRetry ? (
            <Button
              variant="outlined"
              disabled={retryDisabled || retryPending}
              onClick={onRetry}
            >
              {retryPending ? "Retrying…" : "Retry same snapshot"}
            </Button>
          ) : null}
          {run.model_version_id && onOpenEvaluation ? (
            <Button variant="contained" onClick={onOpenEvaluation}>
              Open evaluation
            </Button>
          ) : null}
        </Stack>
      </Stack>

      {presentation.isActive ? (
        <LinearProgress
          variant={
            presentation.progressPercent > 0 ? "determinate" : "indeterminate"
          }
          value={presentation.progressPercent}
          aria-label="Training progress"
        />
      ) : null}

      {run.status === "cancelling" ? (
        <Alert severity="info">
          Cancellation requested. The worker is finishing its bounded current step.
        </Alert>
      ) : null}
      {run.error ? <Alert severity="error">{run.error}</Alert> : null}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile
            label="Training loss"
            value={formatTrainingMetricNumber(metrics.trainLoss)}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile
            label="Validation loss"
            value={formatTrainingMetricNumber(metrics.valLoss)}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile label="Precision" value={percent(metrics.precision)} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile label="Recall" value={percent(metrics.recall)} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile label="mAP50" value={percent(metrics.map50)} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile label="mAP50–95" value={percent(metrics.map50_95)} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile
            label="Epoch duration"
            value={formatTrainingDurationSeconds(metrics.epochDurationSeconds)}
            description="Average per completed epoch"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile
            label="GPU utilization"
            value={formatGpuUtilization(metrics.gpuUtilization)}
            description="When reported by trainer"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile
            label="Best epoch"
            value={metrics.bestEpoch == null ? "—" : String(metrics.bestEpoch)}
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile label="Checkpoint" value={metrics.checkpointStatus} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <MetricTile label="Evaluation" value={metrics.evaluationStatus} />
        </Grid>
      </Grid>
    </Stack>
  );
}
