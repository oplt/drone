import { useState, type ReactNode } from "react";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Card, CardContent, Tab, Tabs, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { VideoDetection } from "../types";
import {
  AnalysisInferenceSection,
  AnalysisSourceSection,
  type AnalysisControlsProps,
} from "./AnalysisControls";
import { AnalysisResultsSection, type AnalysisStatusProps } from "./AnalysisStatus";

type AnalysisWorkflowTabsProps = AnalysisControlsProps &
  AnalysisStatusProps & {
    detections?: VideoDetection[];
    metadataReady?: boolean;
  };

export function AnalysisWorkflowTabs(props: AnalysisWorkflowTabsProps) {
  const [tab, setTab] = useState<"source" | "run" | "evidence">("source");
  const metadataReady = props.metadataReady ?? Boolean(props.video?.captured_at);

  return (
    <Card variant="outlined">
      <CardContent sx={{ pb: 1 }}>
        <Tabs
          value={tab}
          onChange={(_event, value: "source" | "run" | "evidence") => setTab(value)}
          sx={{ mb: 1, borderBottom: 1, borderColor: "divider" }}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="Video analysis workflow"
        >
          <Tab
            value="source"
            label="Source"
            id="video-analysis-tab-source"
            aria-controls="video-analysis-panel-source"
          />
          <Tab
            value="run"
            label="Run"
            id="video-analysis-tab-run"
            aria-controls="video-analysis-panel-run"
          />
          <Tab
            value="evidence"
            label="Evidence"
            id="video-analysis-tab-evidence"
            aria-controls="video-analysis-panel-evidence"
          />
        </Tabs>

        {tab === "source" ? (
          <Box
            role="tabpanel"
            id="video-analysis-panel-source"
            aria-labelledby="video-analysis-tab-source"
          >
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Select a mission recording or upload footage. Capture time must be
              set before analysis for trustworthy georeferencing.
            </Typography>
            <AnalysisSourceSection {...props} />
            {props.video && !metadataReady ? (
              <Alert severity="warning" sx={{ mt: 1.5 }}>
                Capture metadata is incomplete. Save captured-at before running
                analysis.
              </Alert>
            ) : null}
          </Box>
        ) : null}

        {tab === "run" ? (
          <Box
            role="tabpanel"
            id="video-analysis-panel-run"
            aria-labelledby="video-analysis-tab-run"
          >
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Choose the detection model and sampling settings, then run analysis.
            </Typography>
            {!metadataReady ? (
              <Alert severity="error" sx={{ mb: 1.5 }}>
                Analysis is blocked until capture metadata includes a captured-at
                time. Return to Source and save metadata.
              </Alert>
            ) : null}
            <AnalysisInferenceSection
              {...props}
              analyzeDisabled={!props.video || !metadataReady}
            />
          </Box>
        ) : null}

        {tab === "evidence" ? (
          <Box
            role="tabpanel"
            id="video-analysis-panel-evidence"
            aria-labelledby="video-analysis-tab-evidence"
          >
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Track job progress and review detections when ready.
            </Typography>
            <AnalysisResultsSection
              job={props.job}
              detectionCount={props.detectionCount}
              cancelling={props.cancelling}
              onCancel={props.onCancel}
              video={props.video}
              detections={props.detections}
            />
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Collapsible forensic logs wrapper used by VideoAnalysisPanel. */
export function CollapsibleDetectionLogs({
  children,
  defaultExpanded = false,
}: {
  children: ReactNode;
  defaultExpanded?: boolean;
}) {
  return (
    <Accordion defaultExpanded={defaultExpanded} disableGutters>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle2">Detection logs (forensic)</Typography>
      </AccordionSummary>
      <AccordionDetails>{children}</AccordionDetails>
    </Accordion>
  );
}
