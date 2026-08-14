import { RocketLaunch } from "@mui/icons-material";
import {
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import type { VisionTrainingRun } from "../visionTypes";
import { buildVisionTrainingRunListPresentation } from "../trainingRunPresentation";

export function VisionTrainingRunListCard({
  run,
  detailHref,
  onCancel,
  cancelPending,
  onRetry,
  retryDisabled,
  retryPending,
}: {
  run: VisionTrainingRun;
  detailHref: string;
  onCancel?: () => void;
  cancelPending?: boolean;
  onRetry?: () => void;
  retryDisabled?: boolean;
  retryPending?: boolean;
}) {
  const presentation = buildVisionTrainingRunListPresentation(run);

  return (
    <Card variant="outlined">
      <CardActionArea component={RouterLink} to={detailHref}>
        <CardContent>
          <Stack spacing={1}>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              justifyContent="space-between"
              spacing={1}
            >
              <Stack spacing={0.5}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Typography fontWeight={600}>
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
                      label="Evaluated"
                      color="success"
                      variant="outlined"
                    />
                  ) : null}
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  Epoch {presentation.epochLabel} · {presentation.device} ·{" "}
                  {Math.round(presentation.progressPercent)}%
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1} onClick={(event) => event.stopPropagation()}>
                {presentation.isCancellable && onCancel ? (
                  <Button
                    size="small"
                    color="warning"
                    disabled={cancelPending}
                    onClick={onCancel}
                  >
                    {cancelPending ? "Cancelling…" : "Cancel"}
                  </Button>
                ) : null}
                {presentation.isRetryable && onRetry ? (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={retryDisabled || retryPending}
                    onClick={onRetry}
                  >
                    {retryPending ? "Retrying…" : "Retry"}
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
              />
            ) : null}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
