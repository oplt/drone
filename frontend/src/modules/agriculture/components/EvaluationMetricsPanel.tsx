import {
  Alert,
  Box,
  Card,
  CardContent,
  Grid,
  Tooltip,
  Typography,
} from "@mui/material";
import { BarChart } from "@mui/x-charts/BarChart";
import type { EvaluationArtifact, ModelEvaluation } from "../visionTypes";
import { EVALUATION_METRICS, percent } from "../evaluationDisplay";
import { resolveVisionMediaUrl } from "../visionApi";

export function EvaluationMetricsPanel({
  data,
  artifacts,
}: {
  data: ModelEvaluation;
  artifacts: Map<string, EvaluationArtifact>;
}) {
  const confusion = artifacts.get("confusion_matrix_normalized") ?? artifacts.get("confusion_matrix");
  return (
    <>
      <Grid container spacing={2}>
        {EVALUATION_METRICS.map((metric) => (
          <Grid key={metric.key} size={{ xs: 12, sm: 6, lg: 3 }}>
            <Card variant="outlined">
              <CardContent>
                <Tooltip title={metric.description} placement="top-start">
                  <Typography color="text.secondary" variant="body2">{metric.label}</Typography>
                </Tooltip>
                <Typography variant="h4" mt={1}>{percent(data.summary[metric.key])}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
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
