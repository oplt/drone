import { Stack } from "@mui/material";
import { AnalysisInferenceSection } from "./AnalysisInferenceSection";
import { AnalysisSourceSection } from "./AnalysisSourceSection";
import type { AnalysisControlsProps } from "./analysisControlsTypes";

export type { AnalysisControlsProps } from "./analysisControlsTypes";
export { AnalysisInferenceSection } from "./AnalysisInferenceSection";
export { AnalysisSourceSection } from "./AnalysisSourceSection";

export function AnalysisControls(props: AnalysisControlsProps) {
  return (
    <Stack spacing={2}>
      <AnalysisSourceSection {...props} />
      <AnalysisInferenceSection {...props} />
    </Stack>
  );
}
