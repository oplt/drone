import { ModelTraining } from "@mui/icons-material";
import {
  Alert,
  Button,
  Card,
  CardContent,
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
import { VisionCurationQualityAlerts } from "./VisionCurationQualityAlerts";
import { VisionTrainingRunListCard } from "./VisionTrainingRunListCard";

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
  const leakageBlocked = Boolean(
    dataset?.curation_summary?.split_leakage_risk ||
      dataset?.curation_summary?.quality_flags?.split_leakage_risk,
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
              <Alert severity={ready && !leakageBlocked ? "success" : "info"}>
                {leakageBlocked
                  ? "Dataset quality flags block training until split leakage is resolved."
                  : ready
                    ? dataset.status === "locked"
                      ? "This immutable snapshot is ready to train again. Every retry creates a new run and preserves prior attempt history."
                      : "Dataset is ready. Starting training locks this version and its deterministic splits."
                    : `Review every selected image (${dataset.reviewed_count}/${dataset.selected_count} reviewed; at least 3 selected required).`}
              </Alert>
            ) : (
              <Alert severity="warning">Create a dataset first.</Alert>
            )}
            <VisionCurationQualityAlerts
              summary={dataset?.curation_summary}
              context="training"
            />
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
                disabled={!ready || leakageBlocked || !dataset || start.isPending || hasActiveRun}
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
        <Typography variant="subtitle2">Training runs</Typography>
        {runs.data?.length ? (
          runs.data.map((run) => (
            <VisionTrainingRunListCard
              key={run.id}
              run={run}
              detailHref={`/dashboard/agriculture/vision-models/training-runs/${run.id}`}
              onCancel={() => cancel.mutate(run.id)}
              cancelPending={cancel.isPending && cancel.variables === run.id}
              onRetry={() =>
                start.mutate({
                  projectId,
                  payload: {
                    dataset_id: run.dataset_id,
                    base_model: run.base_model as "yolo26n.pt" | "yolo26s.pt",
                    preset: run.preset as "fast" | "balanced" | "high_accuracy",
                  },
                })
              }
              retryDisabled={hasActiveRun}
              retryPending={start.isPending}
            />
          ))
        ) : (
          <Alert severity="info">No training runs yet. Start one when the dataset is ready.</Alert>
        )}
      </Stack>
      {cancel.error ? <Alert severity="error">{cancel.error.message}</Alert> : null}
    </Stack>
  );
}
