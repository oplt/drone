import { Alert, Button, Chip, LinearProgress, Stack, Typography } from "@mui/material";

export function AnalysisRunProgress({
  status,
  progress,
  error,
  stages = [],
  onReplay,
  replayPending = false,
  onRetryStage,
  retryStagePending,
}: {
  status: string;
  progress: number;
  error?: string | null;
  stages?: Array<Record<string, unknown>>;
  onReplay?: () => void;
  replayPending?: boolean;
  onRetryStage?: (stageName: string) => void;
  retryStagePending?: string | null;
}) {
  const percent = Math.max(
    0,
    Math.min(100, progress <= 1 ? progress * 100 : progress),
  );
  return (
    <Stack
      component="section"
      aria-labelledby="analysis-run-progress-heading"
      spacing={0.5}
    >
      <Stack direction="row" justifyContent="space-between">
        <Typography id="analysis-run-progress-heading" variant="subtitle2">
          Analysis run progress
        </Typography>
        <Typography variant="caption" aria-live="polite">
          {status} · {Math.round(percent)}%
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={percent}
        aria-label="Analysis progress"
      />
      {error ? <Alert severity="error" action={onReplay ? <Button size="small" onClick={onReplay} disabled={replayPending}>{replayPending ? "Replaying…" : "Replay run"}</Button> : undefined}>{error}</Alert> : null}
      {stages.length ? (
        <Stack component="ol" aria-label="Analysis stages" spacing={0.5} sx={{ m: 0, pl: 2.5 }}>
          {stages.map((stage) => {
            const stageStatus = String(stage.status ?? "queued");
            const stageProgress = Number(stage.progress ?? 0);
            return (
              <Stack component="li" key={String(stage.id ?? stage.stage_name)} direction="row" spacing={1} alignItems="center">
                <Typography variant="caption" sx={{ minWidth: 170 }}>{String(stage.stage_name ?? "stage").replaceAll("_", " ")}</Typography>
                <Chip size="small" label={`${stageStatus} · ${Math.round(stageProgress <= 1 ? stageProgress * 100 : stageProgress)}%`} color={stageStatus === "completed" ? "success" : stageStatus === "failed" ? "error" : "default"} />
                {stage.error ? <Typography variant="caption" color="error">{String(stage.error)}</Typography> : null}
                {stage.dead_letter ? <Typography variant="caption" color="error">Dead letter</Typography> : null}
                {onRetryStage && ["failed", "dead_letter"].includes(stageStatus) ? <Button size="small" onClick={() => onRetryStage(String(stage.stage_name))} disabled={retryStagePending === String(stage.stage_name)}>{retryStagePending === String(stage.stage_name) ? "Retrying…" : "Retry stage"}</Button> : null}
              </Stack>
            );
          })}
        </Stack>
      ) : null}
    </Stack>
  );
}
