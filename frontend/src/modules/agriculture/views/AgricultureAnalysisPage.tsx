import {
  Alert,
  Button,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { Link as RouterLink, useParams } from "react-router-dom";
import { AgricultureActionExportPanel } from "../components/AgricultureActionExportPanel";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureCropInsightsPanel } from "../components/AgricultureCropInsightsPanel";
import { AgricultureGovernanceAssistantPanel } from "../components/AgricultureGovernanceAssistantPanel";
import { AgricultureReviewWorkspace } from "../components/AgricultureReviewWorkspace";
import { AgricultureSensorFusionPanel } from "../components/AgricultureSensorFusionPanel";
import { AnalysisRunProgress } from "../components/AnalysisRunProgress";
import { useAgricultureAnalysisQuality, useAgricultureAnalysisRun, useReplayAgricultureAnalysisRun, useRetryAgricultureAnalysisStage } from "../hooks";
import { AgricultureReportPanel } from "../components/AgricultureReportPanel";
import { AgricultureMediaTimelinePanel } from "../components/AgricultureMediaTimelinePanel";
import { AgricultureSensorCalibrationWizard } from "../components/AgricultureSensorCalibrationWizard";
import { AgricultureModelRegistryPanel } from "../components/AgricultureModelRegistryPanel";

export default function AgricultureAnalysisPage() {
  const runId = useParams<{ runId: string }>().runId ?? null;
  const run = useAgricultureAnalysisRun(runId);
  const quality = useAgricultureAnalysisQuality(runId);
  const replay = useReplayAgricultureAnalysisRun();
  const retryStage = useRetryAgricultureAnalysisStage();
  if (!runId) return <Alert severity="error">Invalid analysis run.</Alert>;
  if (run.isLoading)
    return (
      <Stack role="status" direction="row" spacing={1} p={3}>
        <CircularProgress size={18} />
        <Typography>Loading analysis…</Typography>
      </Stack>
    );
  if (run.isError || !run.data)
    return <Alert severity="error">Analysis run unavailable.</Alert>;
  return (
    <AgricultureAccessibilityBoundary>
      <Stack
        spacing={2}
        sx={{ p: { xs: 1, md: 3 }, maxWidth: 1440, mx: "auto" }}
      >
        <Button
          component={RouterLink}
          to={`/dashboard/agriculture/flights/${run.data.flight_id}`}
          sx={{ alignSelf: "flex-start" }}
        >
          ← Flight {run.data.flight_id}
        </Button>
        <div>
          <Typography variant="h4" component="h1">
            Agriculture analysis
          </Typography>
          <Typography color="text.secondary">Run {runId}</Typography>
        </div>
        <AnalysisRunProgress
          status={run.data.status}
          progress={run.data.progress}
          error={run.data.error}
          stages={quality.data?.stages ?? []}
          onReplay={[
            "failed",
            "cancelled",
            "blocked_quality",
          ].includes(run.data.status) ? () => replay.mutate(runId) : undefined}
          replayPending={replay.isPending}
          onRetryStage={(stageName) => retryStage.mutate({ runId, stageName })}
          retryStagePending={retryStage.isPending ? retryStage.variables?.stageName : null}
        />
        <AgricultureReportPanel runId={runId} />
        <AgricultureMediaTimelinePanel flightId={run.data.flight_id} />
        <AgricultureReviewWorkspace runId={runId} />
        <AgricultureSensorFusionPanel
          flightId={run.data.flight_id}
          runId={runId}
          active={false}
        />
        <AgricultureSensorCalibrationWizard />
        <AgricultureModelRegistryPanel />
        <AgricultureCropInsightsPanel runId={runId} />
        <AgricultureActionExportPanel runId={runId} />
        <AgricultureGovernanceAssistantPanel runId={runId} />
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
