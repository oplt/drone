import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Grid,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import { AgricultureActionExportPanel } from "../components/AgricultureActionExportPanel";
import { AgricultureAccessibilityBoundary } from "../components/AgricultureAccessibilityBoundary";
import { AgricultureInsightsWorkspace } from "../components/AgricultureInsightsWorkspace";
import { AgricultureGovernanceAssistantPanel } from "../components/AgricultureGovernanceAssistantPanel";
import { AgricultureReviewWorkspace } from "../components/AgricultureReviewWorkspace";
import { PrioritizedFindingsPanel } from "../components/PrioritizedFindingsPanel";
import { AgricultureSensorFusionPanel } from "../components/AgricultureSensorFusionPanel";
import { AnalysisRunProgress } from "../components/AnalysisRunProgress";
import { AgricultureInferenceReuseNotice } from "../components/AgricultureInferenceReuseNotice";
import {
  useAgricultureAnalysisQuality,
  useAgricultureAnalysisRun,
  useReplayAgricultureAnalysisRun,
  useRetryAgricultureAnalysisStage,
} from "../hooks";
import { AgricultureReportPanel } from "../components/AgricultureReportPanel";
import { AgricultureMediaTimelinePanel } from "../components/AgricultureMediaTimelinePanel";
import { AgricultureSensorCalibrationWizard } from "../components/AgricultureSensorCalibrationWizard";
import { AgricultureModelRegistryPanel } from "../components/AgricultureModelRegistryPanel";
import { AgricultureJourneyStepper } from "../components/AgricultureJourneyStepper";
import { isAnalysisRunReplayable } from "../workflows/analysisRunStatusPresentation";
import { FeatureState } from "../../../shared/ui/FeatureState";

export default function AgricultureAnalysisPage() {
  const runId = useParams<{ runId: string }>().runId ?? null;
  const run = useAgricultureAnalysisRun(runId);
  const quality = useAgricultureAnalysisQuality(runId);
  const replay = useReplayAgricultureAnalysisRun();
  const retryStage = useRetryAgricultureAnalysisStage();
  const [tab, setTab] = useState(0);
  if (!runId) return <Alert severity="error">Invalid analysis run.</Alert>;
  return (
    <AgricultureAccessibilityBoundary>
      <Stack
        spacing={2}
        sx={{ p: { xs: 1, md: 3 }, maxWidth: 1440, mx: "auto" }}
      >
        <FeatureState
          loading={run.isLoading}
          error={run.isError || !run.data ? "Analysis run unavailable." : null}
          onRetry={() => void run.refetch()}
        >
          {run.data ? (
            <>
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
                <Typography color="text.secondary">
                  Map and evidence first. Specialist tools stay under Advanced.
                </Typography>
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
                qualityGate={run.data.quality_gate}
                retryCount={run.data.retry_count}
                createdAt={run.data.created_at}
                onReplay={
                  isAnalysisRunReplayable(run.data.status)
                    ? () => replay.mutate(runId)
                    : undefined
                }
                replayPending={replay.isPending}
                onRetryStage={(stageName) =>
                  retryStage.mutate({ runId, stageName })
                }
                retryStagePending={
                  retryStage.isPending ? retryStage.variables?.stageName : null
                }
              />
              <AgricultureInferenceReuseNotice reuse={run.data.inference_reuse} />
              <Tabs
                value={tab}
                onChange={(_event, value: number) => setTab(value)}
                aria-label="Analysis workspace sections"
                variant="scrollable"
                allowScrollButtonsMobile
              >
                <Tab
                  label="Findings"
                  id="analysis-tab-0"
                  aria-controls="analysis-panel-0"
                />
                <Tab
                  label="Insights"
                  id="analysis-tab-1"
                  aria-controls="analysis-panel-1"
                />
                <Tab
                  label="Actions"
                  id="analysis-tab-2"
                  aria-controls="analysis-panel-2"
                />
                <Tab
                  label="Advanced"
                  id="analysis-tab-3"
                  aria-controls="analysis-panel-3"
                />
              </Tabs>
              <Stack
                role="tabpanel"
                id={`analysis-panel-${tab}`}
                aria-labelledby={`analysis-tab-${tab}`}
                spacing={2}
              >
                {tab === 0 ? (
                  <Grid container spacing={2} alignItems="flex-start">
                    <Grid size={{ xs: 12, lg: 8 }}>
                      <AgricultureReviewWorkspace runId={runId} />
                    </Grid>
                    <Grid
                      size={{ xs: 12, lg: 4 }}
                      sx={{
                        maxHeight: { lg: "calc(100vh - 12rem)" },
                        overflow: { lg: "auto" },
                      }}
                    >
                      <PrioritizedFindingsPanel runId={runId} showHotspotMap={false} />
                    </Grid>
                    <Grid size={12}>
                      <AgricultureReportPanel runId={runId} />
                    </Grid>
                  </Grid>
                ) : null}
                {tab === 1 ? (
                  <AgricultureInsightsWorkspace run={run.data} />
                ) : null}
                {tab === 2 ? (
                  <AgricultureActionExportPanel runId={runId} />
                ) : null}
                {tab === 3 ? (
                  <Stack spacing={2}>
                    <Alert severity="info">
                      Specialist tools for operators. Findings and actions stay
                      on the primary tabs.
                    </Alert>
                    <AgricultureMediaTimelinePanel flightId={run.data.flight_id} />
                    <AgricultureSensorFusionPanel
                      flightId={run.data.flight_id}
                      runId={runId}
                      active={false}
                    />
                    <AgricultureGovernanceAssistantPanel runId={runId} />
                    <Accordion disableGutters>
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Typography variant="subtitle2">
                          Calibration & model registry
                        </Typography>
                      </AccordionSummary>
                      <AccordionDetails>
                        <Stack spacing={2}>
                          <AgricultureSensorCalibrationWizard />
                          <AgricultureModelRegistryPanel />
                        </Stack>
                      </AccordionDetails>
                    </Accordion>
                  </Stack>
                ) : null}
              </Stack>
            </>
          ) : null}
        </FeatureState>
      </Stack>
    </AgricultureAccessibilityBoundary>
  );
}
