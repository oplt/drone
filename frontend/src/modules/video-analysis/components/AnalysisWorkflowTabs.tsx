import { useState } from "react";
import { Box, Card, CardContent, Tab, Tabs, Typography } from "@mui/material";
import {
  AnalysisInferenceSection,
  AnalysisSourceSection,
  type AnalysisControlsProps,
} from "./AnalysisControls";
import { AnalysisResultsSection, type AnalysisStatusProps } from "./AnalysisStatus";

type AnalysisWorkflowTabsProps = AnalysisControlsProps & AnalysisStatusProps;

export function AnalysisWorkflowTabs(props: AnalysisWorkflowTabsProps) {
  const [tab, setTab] = useState<"source" | "inference" | "results">("source");

  return (
    <Card variant="outlined">
      <CardContent sx={{ pb: 1 }}>
        <Tabs
          value={tab}
          onChange={(_event, value: "source" | "inference" | "results") => setTab(value)}
          sx={{ mb: 1, borderBottom: 1, borderColor: "divider" }}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab value="source" label="Source" />
          <Tab value="inference" label="Inference" />
          <Tab value="results" label="Results" />
        </Tabs>

        {tab === "source" ? (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Upload a flight recording to analyze offline.
            </Typography>
            <AnalysisSourceSection {...props} />
          </Box>
        ) : null}

        {tab === "inference" ? (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Choose the detection model and sampling settings, then run analysis.
            </Typography>
            <AnalysisInferenceSection {...props} />
          </Box>
        ) : null}

        {tab === "results" ? (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Track job progress and review when detections are ready.
            </Typography>
            <AnalysisResultsSection job={props.job} detectionCount={props.detectionCount} />
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}
