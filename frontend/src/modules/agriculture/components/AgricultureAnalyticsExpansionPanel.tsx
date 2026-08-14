import { Alert, Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import {
  useAgricultureAnalysisReadiness,
  useAgricultureSpatialLayers,
} from "../hooks";
import type { AgricultureAnalysisRun } from "../types";

function number(value: unknown, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "—";
}

function AnalyticsCard({
  title,
  status,
  children,
}: {
  title: string;
  status: string;
  children: React.ReactNode;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, height: "100%" }}>
      <Stack spacing={1}>
        <Stack direction="row" justifyContent="space-between" spacing={1}>
          <Typography variant="subtitle2">{title}</Typography>
          <Chip
            size="small"
            label={status.replaceAll("_", " ")}
            color={status === "ready" || status === "pass" ? "success" : "warning"}
          />
        </Stack>
        {children}
      </Stack>
    </Paper>
  );
}

export function AgricultureAnalyticsExpansionPanel({
  run,
}: {
  run: AgricultureAnalysisRun;
}) {
  const layers = useAgricultureSpatialLayers(run.id);
  const readiness = useAgricultureAnalysisReadiness(run.flight_id);
  const byName = new Map(
    (layers.data?.layers ?? []).map((layer) => [layer.layer, layer]),
  );
  const gaps = byName.get("stand_gap");
  const spacing = byName.get("plant_spacing");
  const weeds = byName.get("weed_density");
  const experiment = byName.get("crop_weed_segmentation_experiment");
  const plugins = (readiness.data?.capabilities ?? []).filter((capability) =>
    ["fruit_counting", "ripeness_classification"].includes(capability.id),
  );
  return (
    <Stack spacing={1.5} component="section" aria-labelledby="analytics-expansion-heading">
      <div>
        <Typography id="analytics-expansion-heading" variant="h6">
          Stand, weed & crop-specific analytics
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Metric products expose their geometry, configured assumptions, source
          quality, and release limits. Missing context stays visibly blocked.
        </Typography>
      </div>
      {layers.isError ? (
        <Alert severity="warning">Analytics layer summaries are unavailable.</Alert>
      ) : null}
      <Grid container spacing={1.5}>
        <Grid size={{ xs: 12, md: 4 }}>
          <AnalyticsCard title="Stand gaps" status={gaps?.status ?? "not_measured"}>
            <Typography variant="body2">
              {String(gaps?.summary.count ?? 0)} gaps · affected area {number(gaps?.summary.area_m2)} m²
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Crop/spacing assumptions: {JSON.stringify(gaps?.summary.assumptions ?? {})}
            </Typography>
            {(gaps?.summary.quality_warnings as string[] | undefined)?.length ? (
              <Alert severity="warning">
                {(gaps?.summary.quality_warnings as string[]).join(", ").replaceAll("_", " ")}
              </Alert>
            ) : null}
          </AnalyticsCard>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <AnalyticsCard title="Plant spacing" status={spacing?.status ?? "not_measured"}>
            <Typography variant="body2">
              Median {number(spacing?.summary.median_spacing_m)} m · IQR {number(spacing?.summary.dispersion_iqr_m)} m
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {String(spacing?.summary.sample_count ?? 0)} adjacent pairs · {String(spacing?.summary.statistical_outlier_count ?? 0)} statistical outliers
            </Typography>
          </AnalyticsCard>
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <AnalyticsCard title="Weed density" status={weeds?.status ?? "not_measured"}>
            <Typography variant="body2">
              {number(weeds?.summary.field_density_detections_per_m2, 4)} detections/m² · {String(weeds?.summary.hotspot_count ?? 0)} hotspots
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Grid {number(weeds?.summary.cell_size_m, 0)} m · change {JSON.stringify(weeds?.summary.change_vs_previous ?? "no comparable baseline")}
            </Typography>
          </AnalyticsCard>
        </Grid>
      </Grid>
      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Stack spacing={1}>
          <Typography variant="subtitle2">Crop-specific model plugins</Typography>
          {plugins.map((capability) => (
            <Stack key={capability.id} spacing={0.5}>
              <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                <Chip
                  size="small"
                  label={capability.label}
                  color={capability.available ? "success" : "default"}
                />
                <Typography variant="caption">
                  {capability.available
                    ? "Released for this crop and capture contract"
                    : capability.unavailable_reasons.join(" ")}
                </Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Limits: {capability.limitations?.join(" ") || "No released contract."}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Paper>
      <Alert severity={experiment?.summary.benefit_demonstrated ? "success" : "info"}>
        Crop-vs-weed segmentation: {experiment
          ? `${String(experiment.summary.status).replaceAll("_", " ")}. Production remains disabled pending architecture and safety review.`
          : "research experiment not evaluated. Detection-based density remains the production approximation."}
      </Alert>
    </Stack>
  );
}
