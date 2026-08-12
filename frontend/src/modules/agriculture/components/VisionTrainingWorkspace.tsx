import { ModelTraining, RocketLaunch } from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useCancelVisionTraining,
  useStartVisionTraining,
  useVisionTrainingRuns,
} from "../hooks/useVisionModels";
import type { VisionDataset } from "../visionTypes";

export function VisionTrainingWorkspace({
  projectId,
  dataset,
}: {
  projectId: string;
  dataset: VisionDataset | null;
}) {
  const runs = useVisionTrainingRuns(projectId);
  const start = useStartVisionTraining();
  const cancel = useCancelVisionTraining();
  const [baseModel, setBaseModel] = useState<"yolo26n.pt" | "yolo26s.pt">(
    "yolo26s.pt",
  );
  const [preset, setPreset] = useState<"fast" | "balanced" | "high_accuracy">(
    "balanced",
  );
  const ready = Boolean(
    dataset &&
      dataset.selected_count >= 3 &&
      dataset.reviewed_count >= dataset.selected_count,
  );
  const hasActiveRun = Boolean(
    runs.data?.some((run) => ["queued", "running", "cancelling"].includes(run.status)),
  );
  return (
    <Stack spacing={3}>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6">Train crop-specific detector</Typography>
            {dataset ? (
              <Alert severity={ready ? "success" : "info"}>
                {ready
                  ? dataset.status === "locked"
                    ? "This immutable snapshot is ready to train again. Every retry creates a new run and preserves prior attempt history."
                    : "Dataset is ready. Starting training locks this version and its deterministic splits."
                  : `Review every selected image (${dataset.reviewed_count}/${dataset.selected_count} reviewed; at least 3 selected required).`}
              </Alert>
            ) : (
              <Alert severity="warning">Create a dataset first.</Alert>
            )}
            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
              <TextField
                select
                size="small"
                label="Base model"
                value={baseModel}
                onChange={(event) => setBaseModel(event.target.value as typeof baseModel)}
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="yolo26n.pt">YOLO26n · fast</MenuItem>
                <MenuItem value="yolo26s.pt">YOLO26s · balanced</MenuItem>
              </TextField>
              <TextField
                select
                size="small"
                label="Preset"
                value={preset}
                onChange={(event) => setPreset(event.target.value as typeof preset)}
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="fast">Fast</MenuItem>
                <MenuItem value="balanced">Balanced</MenuItem>
                <MenuItem value="high_accuracy">High accuracy</MenuItem>
              </TextField>
              <Button
                variant="contained"
                startIcon={<ModelTraining />}
                disabled={!ready || !dataset || start.isPending || hasActiveRun}
                onClick={() =>
                  dataset &&
                  start.mutate({
                    projectId,
                    payload: { dataset_id: dataset.id, base_model: baseModel, preset },
                  })
                }
              >
                Start training
              </Button>
            </Stack>
            {start.error ? <Alert severity="error">{start.error.message}</Alert> : null}
          </Stack>
        </CardContent>
      </Card>
      <Stack spacing={1.5}>
        {runs.data?.map((run) => (
          <Card key={run.id} variant="outlined">
            <CardContent>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                <Box flex={1}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography fontWeight={600}>{run.base_model} · {run.preset}</Typography>
                    <Chip
                      size="small"
                      label={run.status}
                      color={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "default"}
                    />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    Epoch {run.current_epoch}/{run.total_epochs} · {run.device}
                  </Typography>
                  {["queued", "running", "cancelling"].includes(run.status) ? (
                    <LinearProgress variant={run.progress > 0 ? "determinate" : "indeterminate"} value={run.progress} sx={{ mt: 1 }} />
                  ) : null}
                  {run.status === "cancelling" ? (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                      Cancellation requested. The worker is finishing its bounded current step.
                    </Typography>
                  ) : null}
                  {run.error ? <Alert severity="error" sx={{ mt: 1 }}>{run.error}</Alert> : null}
                </Box>
                <Stack spacing={1} alignItems={{ md: "flex-end" }}>
                  {run.model_version_id ? (
                    <Chip icon={<RocketLaunch />} label="Evaluation completed" color="success" variant="outlined" />
                  ) : null}
                  {["queued", "running"].includes(run.status) ? (
                    <Button
                      size="small"
                      color="warning"
                      disabled={cancel.isPending}
                      onClick={() => cancel.mutate(run.id)}
                    >
                      {cancel.isPending && cancel.variables === run.id ? "Cancelling…" : "Cancel run"}
                    </Button>
                  ) : null}
                  {["failed", "cancelled"].includes(run.status) ? (
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={start.isPending || hasActiveRun}
                      onClick={() => start.mutate({
                        projectId,
                        payload: {
                          dataset_id: run.dataset_id,
                          base_model: run.base_model as "yolo26n.pt" | "yolo26s.pt",
                          preset: run.preset as "fast" | "balanced" | "high_accuracy",
                        },
                      })}
                    >
                      Retry same snapshot
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>
      {cancel.error ? <Alert severity="error">{cancel.error.message}</Alert> : null}
    </Stack>
  );
}
