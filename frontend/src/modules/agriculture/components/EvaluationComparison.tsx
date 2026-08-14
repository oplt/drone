import { CompareArrows } from "@mui/icons-material";
import { Box, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { metricSummary, percent } from "../evaluationDisplay";
import {
  formatMetricDelta,
  visibleComparisonMetrics,
} from "../evaluationMetricDeltas";
import type { MetricSummary, VisionModelVersion } from "../visionTypes";

export function EvaluationComparison({
  siblings,
  current,
  comparisonId,
  setComparisonId,
  productionVersionId,
}: {
  siblings: VisionModelVersion[];
  current: MetricSummary;
  comparisonId: string;
  setComparisonId: (id: string) => void;
  productionVersionId?: string;
}) {
  const comparison = siblings.find((item) => item.id === comparisonId);
  const priorSummary = comparison ? metricSummary(comparison) : null;
  if (!siblings.length) return null;
  const metrics =
    priorSummary != null
      ? visibleComparisonMetrics(current, priorSummary)
      : visibleComparisonMetrics(current, {});
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} spacing={2}>
          <CompareArrows color="action" />
          <TextField select size="small" label="Compare with" value={comparisonId} onChange={(event) => setComparisonId(event.target.value)} sx={{ minWidth: 260 }}>
            <MenuItem value="">Select version</MenuItem>
            {siblings.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                v{item.version} · {item.status}
                {item.id === productionVersionId ? " (production)" : ""}
              </MenuItem>
            ))}
          </TextField>
          {comparison?.id === productionVersionId ? (
            <Chip size="small" color="success" label="Current production baseline" />
          ) : null}
          {priorSummary ? (
            <Stack direction="row" spacing={3} useFlexGap flexWrap="wrap">
              {metrics.map((metric) => {
                const value = current[metric.key];
                const prior = priorSummary[metric.key];
                const delta = formatMetricDelta(metric, value, prior);
                return (
                  <Box key={metric.key}>
                    <Typography variant="caption" color="text.secondary">{metric.label}</Typography>
                    <Typography>
                      {metric.format === "ratio"
                        ? percent(value)
                        : value == null
                          ? "—"
                          : metric.format === "fps"
                            ? `${value.toFixed(1)} FPS`
                            : metric.format === "latency_ms"
                              ? `${value.toFixed(0)} ms`
                              : `${value.toFixed(1)} MB`}
                      {" "}
                      <Typography component="span" color={delta.tone}>
                        ({delta.label})
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
