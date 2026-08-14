import { Alert, Button, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import {
  buildAnalysisRunStatusPresentation,
  buildAnalysisStagePresentations,
  type AnalysisRunStatusInput,
} from "../workflows/analysisRunStatusPresentation";

export function AnalysisRunProgress({
  status,
  progress,
  error,
  stages = [],
  qualityGate,
  retryCount,
  createdAt,
  updatedAt,
  onReplay,
  replayPending = false,
  onRetryStage,
  retryStagePending,
}: AnalysisRunStatusInput & {
  onReplay?: () => void;
  replayPending?: boolean;
  onRetryStage?: (stageName: string) => void;
  retryStagePending?: string | null;
}) {
  const presentation = buildAnalysisRunStatusPresentation({
    status,
    progress,
    error,
    stages,
    qualityGate,
    retryCount,
    createdAt,
    updatedAt,
  });
  const stagePresentations = buildAnalysisStagePresentations(stages);

  return (
    <Stack
      component="section"
      aria-labelledby="analysis-run-progress-heading"
      spacing={0.75}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography id="analysis-run-progress-heading" variant="subtitle2">
          Analysis run progress
        </Typography>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
          <Chip
            size="small"
            label={presentation.label}
            color={presentation.chipColor}
          />
          <Typography variant="caption" aria-live="polite">
            {presentation.summaryLine}
          </Typography>
        </Stack>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={presentation.progressPercent}
        aria-label="Analysis progress"
      />
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {presentation.currentStageLabel ? (
          <Typography variant="caption" color="text.secondary">
            Current stage: {presentation.currentStageLabel}
          </Typography>
        ) : null}
        {presentation.lastUpdatedLabel ? (
          <Typography variant="caption" color="text.secondary">
            Last update: {presentation.lastUpdatedLabel}
          </Typography>
        ) : null}
        {presentation.isCancelling ? (
          <Typography variant="caption" color="warning.main">
            Cancellation in progress
          </Typography>
        ) : null}
        {presentation.isCancelled ? (
          <Typography variant="caption" color="text.secondary">
            Run cancelled
          </Typography>
        ) : null}
        {presentation.retryCount > 0 ? (
          <Typography variant="caption" color="text.secondary">
            Retries: {presentation.retryCount}
          </Typography>
        ) : null}
        {presentation.hasRetryableStages ? (
          <Typography variant="caption" color="text.secondary">
            Retryable stages available
          </Typography>
        ) : null}
      </Stack>
      {presentation.qualityBlocked && presentation.qualityBlockReason ? (
        <Alert severity="warning">
          Quality gate blocked inference: {presentation.qualityBlockReason}
        </Alert>
      ) : null}
      {error ? (
        <Alert
          severity="error"
          action={
            onReplay ? (
              <Button
                size="small"
                onClick={onReplay}
                disabled={replayPending}
              >
                {replayPending ? "Replaying…" : "Replay run"}
              </Button>
            ) : undefined
          }
        >
          {error}
        </Alert>
      ) : null}
      {stagePresentations.length ? (
        <Stack
          component="ol"
          aria-label="Analysis stages"
          spacing={0.5}
          sx={{ m: 0, pl: 2.5 }}
        >
          {stagePresentations.map((stagePresentation, index) => {
            const stage = stages[index]!;
            const stageName = String(stage.stage_name ?? "stage");
            return (
              <Stack
                component="li"
                key={stagePresentation.key}
                direction="row"
                spacing={1}
                alignItems="center"
                flexWrap="wrap"
                useFlexGap
              >
                <Typography variant="caption" sx={{ minWidth: 170 }}>
                  {stagePresentation.name}
                </Typography>
                <Chip
                  size="small"
                  label={`${stagePresentation.label} · ${Math.round(stagePresentation.progressPercent)}%`}
                  color={stagePresentation.chipColor}
                />
                {stagePresentation.error ? (
                  <Typography variant="caption" color="error">
                    {stagePresentation.error}
                  </Typography>
                ) : null}
                {stagePresentation.deadLetter ? (
                  <Typography variant="caption" color="error">
                    Dead letter
                  </Typography>
                ) : null}
                {onRetryStage && stagePresentation.retryable ? (
                  <Button
                    size="small"
                    onClick={() => onRetryStage(stageName)}
                    disabled={retryStagePending === stageName}
                  >
                    {retryStagePending === stageName ? "Retrying…" : "Retry stage"}
                  </Button>
                ) : null}
              </Stack>
            );
          })}
        </Stack>
      ) : null}
    </Stack>
  );
}
