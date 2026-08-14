import { TrendingDown, TrendingFlat, TrendingUp } from "@mui/icons-material";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Grid,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import { EVALUATION_METRICS, percent } from "../evaluationDisplay";
import {
  CORE_COMPARISON_METRICS,
  formatMetricDelta,
  OPTIONAL_COMPARISON_METRICS,
  type MetricComparisonSpec,
} from "../evaluationMetricDeltas";
import type { EvaluationArtifact, MetricSummary, ModelEvaluation } from "../visionTypes";
import { resolveVisionMediaUrl } from "../visionApi";

function DeltaIcon({ direction }: { direction: "better" | "worse" | "equal" | "missing" }) {
  if (direction === "better") return <TrendingUp fontSize="inherit" />;
  if (direction === "worse") return <TrendingDown fontSize="inherit" />;
  return <TrendingFlat fontSize="inherit" />;
}

function metricSpecForKey(key: keyof MetricSummary): MetricComparisonSpec | undefined {
  return [...CORE_COMPARISON_METRICS, ...OPTIONAL_COMPARISON_METRICS].find(
    (metric) => metric.key === key,
  );
}

export function EvaluationMetricsPanel({
  data,
  artifacts,
  baselineSummary,
  baselineLabel,
}: {
  data: ModelEvaluation;
  artifacts: Map<string, EvaluationArtifact>;
  baselineSummary?: MetricSummary;
  baselineLabel?: string;
}) {
  const confusion = artifacts.get("confusion_matrix_normalized") ?? artifacts.get("confusion_matrix");
  return (
    <>
      {baselineSummary && baselineLabel ? (
        <Alert severity="info" sx={{ alignItems: "center" }}>
          Comparing candidate metrics against <strong>{baselineLabel}</strong>.
        </Alert>
      ) : null}
      <Grid container spacing={2}>
        {EVALUATION_METRICS.map((metric) => {
          const spec = metricSpecForKey(metric.key);
          const delta =
            baselineSummary && spec
              ? formatMetricDelta(spec, data.summary[metric.key], baselineSummary[metric.key])
              : null;
          return (
            <Grid key={metric.key} size={{ xs: 12, sm: 6, lg: 3 }}>
              <Card variant="outlined">
                <CardContent>
                  <Tooltip title={metric.description} placement="top-start">
                    <Typography color="text.secondary" variant="body2">{metric.label}</Typography>
                  </Tooltip>
                  <Typography variant="h4" mt={1}>{percent(data.summary[metric.key])}</Typography>
                  {delta && baselineLabel ? (
                    <Stack direction="row" spacing={0.5} alignItems="center" mt={1}>
                      <Box component="span" sx={{ color: delta.tone, display: "inline-flex" }}>
                        <DeltaIcon direction={delta.direction} />
                      </Box>
                      <Typography variant="body2" color={delta.tone}>
                        {delta.label} vs {baselineLabel}
                      </Typography>
                    </Stack>
                  ) : null}
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>Per-class performance</Typography>
              {data.per_class.length ? (
                <BarChart
                  height={290}
                  xAxis={[{ scaleType: "band", data: data.per_class.map((item) => item.class_name.replaceAll("_", " ")) }]}
                  series={[
                    { data: data.per_class.map((item) => (item.precision ?? 0) * 100), label: "Precision" },
                    { data: data.per_class.map((item) => (item.recall ?? 0) * 100), label: "Recall" },
                    { data: data.per_class.map((item) => (item.map50 ?? 0) * 100), label: "mAP50" },
                  ]}
                  yAxis={[{ min: 0, max: 100 }]}
                />
              ) : <Alert severity="info">No per-class metrics were returned.</Alert>}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography variant="h6">Confusion matrix</Typography>
              {confusion ? (
                <Box component="img" src={resolveVisionMediaUrl(confusion.url)} alt="Evaluation confusion matrix" sx={{ width: "100%", maxHeight: 300, objectFit: "contain" }} />
              ) : (
                <Typography color="text.secondary" mt={2}>
                  {data.confusion_matrix ? "The numerical matrix is preserved; no plot was produced." : "No confusion matrix was returned."}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
