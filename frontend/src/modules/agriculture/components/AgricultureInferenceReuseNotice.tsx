import { Alert, Stack, Typography } from "@mui/material";
import {
  formatInferenceReuseHeadline,
  hasReusedInference,
  summarizeReuseDetail,
} from "../inferenceReuseDisplay";
import type { InferenceReuseSummary } from "../workflows/analysis/types";

export function AgricultureInferenceReuseNotice({
  reuse,
}: {
  reuse: InferenceReuseSummary | null | undefined;
}) {
  if (!hasReusedInference(reuse)) {
    return null;
  }
  const summary = reuse;
  const details = summarizeReuseDetail(summary);
  return (
    <Alert severity="info" variant="outlined" sx={{ py: 1 }}>
      <Stack spacing={0.5}>
        <Typography variant="body2">{formatInferenceReuseHeadline(summary)}</Typography>
        <Typography variant="caption" color="text.secondary">
          No reprocessing of identical validated inputs. Aggregation and review data may still be new for this run.
        </Typography>
        {details.map((line) => (
          <Typography key={line} variant="caption" color="text.secondary">
            {line}
          </Typography>
        ))}
      </Stack>
    </Alert>
  );
}
