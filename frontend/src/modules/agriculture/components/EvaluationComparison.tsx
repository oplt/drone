import { CompareArrows } from "@mui/icons-material";
import { Box, Card, CardContent, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { EVALUATION_METRICS, metricSummary, percent } from "../evaluationDisplay";
import type { MetricSummary, VisionModelVersion } from "../visionTypes";

export function EvaluationComparison({
  siblings,
  current,
  comparisonId,
  setComparisonId,
}: {
  siblings: VisionModelVersion[];
  current: MetricSummary;
  comparisonId: string;
  setComparisonId: (id: string) => void;
}) {
  const comparison = siblings.find((item) => item.id === comparisonId);
  const priorSummary = comparison ? metricSummary(comparison) : null;
  if (!siblings.length) return null;
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} spacing={2}>
          <CompareArrows color="action" />
          <TextField select size="small" label="Compare with" value={comparisonId} onChange={(event) => setComparisonId(event.target.value)} sx={{ minWidth: 220 }}>
            <MenuItem value="">Select version</MenuItem>
            {siblings.map((item) => <MenuItem key={item.id} value={item.id}>v{item.version} · {item.status}</MenuItem>)}
          </TextField>
          {priorSummary ? (
            <Stack direction="row" spacing={3}>
              {EVALUATION_METRICS.map((metric) => {
                const value = current[metric.key];
                const prior = priorSummary[metric.key];
                const delta = value != null && prior != null ? value - prior : null;
                return (
                  <Box key={metric.key}>
                    <Typography variant="caption" color="text.secondary">{metric.label}</Typography>
                    <Typography>
                      {percent(value)}{" "}
                      <Typography component="span" color={delta != null && delta >= 0 ? "success.main" : "error.main"}>
                        ({delta == null ? "—" : `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)} pp`})
                      </Typography>
                    </Typography>
                  </Box>
                );
              })}
            </Stack>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
