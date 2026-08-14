import { Alert, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { VisionTrainingRunDetailsPanel } from "../components/VisionTrainingRunDetailsPanel";
import {
  useCancelVisionTraining,
  useStartVisionTraining,
  useVisionModels,
  useVisionTraining,
  useVisionTrainingRuns,
} from "../hooks/useVisionModels";
import { FeatureState } from "../../../shared/ui/FeatureState";

export default function VisionTrainingRunPage() {
  const runId = useParams<{ runId: string }>().runId ?? null;
  const navigate = useNavigate();
  const run = useVisionTraining(runId);
  const runs = useVisionTrainingRuns(run.data?.project_id ?? null);
  const models = useVisionModels();
  const cancel = useCancelVisionTraining();
  const start = useStartVisionTraining();
  const hasActiveRun = Boolean(
    runs.data?.some((item) =>
      ["queued", "running", "cancelling"].includes(item.status),
    ),
  );

  if (!runId) {
    return <Alert severity="error">Invalid training run.</Alert>;
  }

  const backHref = run.data
    ? `/dashboard/agriculture/vision-models?project=${run.data.project_id}&tab=train`
    : "/dashboard/agriculture/vision-models?tab=train";

  return (
    <AgricultureAccessibilityBoundary>
      <Stack spacing={2} sx={{ p: { xs: 1, md: 3 }, maxWidth: 1200, mx: "auto" }}>
        <Button component={RouterLink} to={backHref} sx={{ alignSelf: "flex-start" }}>
          ← Training runs
        </Button>
        <div>
          <Typography variant="h4" component="h1">
            Training run
          </Typography>
          <Typography color="text.secondary">
            Advanced metrics, checkpoint status, and recovery actions.
          </Typography>
        </div>
        <FeatureState
          loading={run.isLoading}
          error={run.isError || !run.data ? "Training run unavailable." : null}
          onRetry={() => void run.refetch()}
        >
          {run.data ? (
            <VisionTrainingRunDetailsPanel
              run={run.data}
              onCancel={() => cancel.mutate(run.data.id)}
              cancelPending={cancel.isPending && cancel.variables === run.data.id}
              onRetry={() =>
                start.mutate({
                  projectId: run.data.project_id,
                  payload: {
                    dataset_id: run.data.dataset_id,
                    base_model: run.data.base_model as "yolo26n.pt" | "yolo26s.pt",
                    preset: run.data.preset as
                      | "fast"
                      | "balanced"
                      | "high_accuracy",
                  },
                })
              }
              retryDisabled={hasActiveRun}
              retryPending={start.isPending}
              onOpenEvaluation={() => {
                const version = models.data?.find(
                  (item) => item.training_run_id === run.data!.id,
                );
                if (!version) {
                  return;
                }
                navigate(
                  `/dashboard/agriculture/vision-models?project=${run.data.project_id}&tab=evaluation&version=${version.id}`,
                );
              }}
            />
          ) : (
            <CircularProgress aria-label="Loading training run" />
          )}
        </FeatureState>
        {cancel.error ? <Alert severity="error">{cancel.error.message}</Alert> : null}
        {start.error ? <Alert severity="error">{start.error.message}</Alert> : null}
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
