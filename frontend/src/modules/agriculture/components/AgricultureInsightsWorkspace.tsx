import { Stack } from "@mui/material";
import type { AgricultureAnalysisRun } from "../types";
import { AgricultureAnalyticsExpansionPanel } from "./AgricultureAnalyticsExpansionPanel";
import { AgricultureCropInsightsPanel } from "./AgricultureCropInsightsPanel";

export function AgricultureInsightsWorkspace({ run }: { run: AgricultureAnalysisRun }) {
  return (
    <Stack spacing={2}>
      <AgricultureAnalyticsExpansionPanel run={run} />
      <AgricultureCropInsightsPanel runId={run.id} />
    </Stack>
  );
}
