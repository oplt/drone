import {
  Alert,
  Button,
  CircularProgress,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { AgricultureActionExportPanel } from "../components/AgricultureActionExportPanel";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureCropInsightsPanel } from "../components/AgricultureCropInsightsPanel";
import { AgricultureGovernanceAssistantPanel } from "../components/AgricultureGovernanceAssistantPanel";
import { AgricultureReviewWorkspace } from "../components/AgricultureReviewWorkspace";
import { PrioritizedFindingsPanel } from "../components/PrioritizedFindingsPanel";
import { AgricultureSensorFusionPanel } from "../components/AgricultureSensorFusionPanel";
import { AnalysisRunProgress } from "../components/AnalysisRunProgress";
import { useAgricultureAnalysisQuality, useAgricultureAnalysisRun, useReplayAgricultureAnalysisRun, useRetryAgricultureAnalysisStage } from "../hooks";
import { AgricultureReportPanel } from "../components/AgricultureReportPanel";
import { AgricultureMediaTimelinePanel } from "../components/AgricultureMediaTimelinePanel";
import { AgricultureSensorCalibrationWizard } from "../components/AgricultureSensorCalibrationWizard";
import { AgricultureModelRegistryPanel } from "../components/AgricultureModelRegistryPanel";
import { AgricultureJourneyStepper } from "../components/AgricultureJourneyStepper";

export default function AgricultureAnalysisPage() {
  const runId = useParams<{ runId: string }>().runId ?? null;
  const run = useAgricultureAnalysisRun(runId);
  const quality = useAgricultureAnalysisQuality(runId);
  const replay = useReplayAgricultureAnalysisRun();
  const retryStage = useRetryAgricultureAnalysisStage();
  const [tab, setTab] = useState(0);
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
        <AgricultureJourneyStepper
          flightStatus="completed"
          analysisStatus={run.data.status}
          analysisRunId={runId}
        />
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
        <Tabs value={tab} onChange={(_event, value: number) => setTab(value)} aria-label="Analysis workspace sections" variant="scrollable" allowScrollButtonsMobile>
          <Tab label="Findings" id="analysis-tab-0" aria-controls="analysis-panel-0" />
          <Tab label="Insights" id="analysis-tab-1" aria-controls="analysis-panel-1" />
          <Tab label="Technical details" id="analysis-tab-2" aria-controls="analysis-panel-2" />
          <Tab label="Governance" id="analysis-tab-3" aria-controls="analysis-panel-3" />
          <Tab label="Actions" id="analysis-tab-4" aria-controls="analysis-panel-4" />
        </Tabs>
        <Stack role="tabpanel" id={`analysis-panel-${tab}`} aria-labelledby={`analysis-tab-${tab}`} spacing={2}>
          {tab === 0 ? (
            <>
              <PrioritizedFindingsPanel runId={runId} />
              <details>
                <summary>
                  <Typography component="span" variant="subtitle2">
                    Full review workspace
                  </Typography>
                </summary>
                <AgricultureReviewWorkspace runId={runId} />
              </details>
              <AgricultureReportPanel runId={runId} />
            </>
          ) : null}
          {tab === 1 ? <AgricultureCropInsightsPanel runId={runId} /> : null}
          {tab === 2 ? (
            <>
              <AgricultureMediaTimelinePanel flightId={run.data.flight_id} />
              <AgricultureSensorFusionPanel flightId={run.data.flight_id} runId={runId} active={false} />
              <AgricultureSensorCalibrationWizard />
              <AgricultureModelRegistryPanel />
            </>
          ) : null}
          {tab === 3 ? <AgricultureGovernanceAssistantPanel runId={runId} /> : null}
          {tab === 4 ? <AgricultureActionExportPanel runId={runId} /> : null}
        </Stack>
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
