import {
  Alert,
  Button,
  Chip,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useAgricultureCropRisks,
  useAgricultureGrowthMetrics,
  useAgricultureGrowthStage,
  useAgricultureYieldForecast,
  useCorrectAgricultureGrowthStage,
  useProcessAgricultureCropRisks,
  useProcessAgricultureGrowthStage,
  useProcessAgricultureYieldForecast,
} from "../hooks";

function pct(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

export function AgricultureCropInsightsPanel({ runId }: { runId: string }) {
  const risks = useAgricultureCropRisks(runId);
  const growth = useAgricultureGrowthMetrics(runId);
  const stage = useAgricultureGrowthStage(runId);
  const forecast = useAgricultureYieldForecast(runId);
  const processRisks = useProcessAgricultureCropRisks();
  const processStage = useProcessAgricultureGrowthStage();
  const processYield = useProcessAgricultureYieldForecast();
  const correctStage = useCorrectAgricultureGrowthStage();
  const [humanStage, setHumanStage] = useState("");
  const busy =
    processRisks.isPending || processStage.isPending || processYield.isPending;
  const evaluate = () => {
    processRisks.mutate({ runId, payload: {} });
    processStage.mutate({ runId, payload: {} });
    processYield.mutate({ runId, payload: {} });
  };
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.25}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          spacing={1}
        >
          <div>
            <Typography variant="subtitle2">Crop insights</Typography>
            <Typography variant="caption" color="text.secondary">
              P4 outputs are applicability-gated; candidates require
              operator/agronomist review.
            </Typography>
          </div>
          <Button
            size="small"
            variant="outlined"
            onClick={evaluate}
            disabled={busy}
          >
            {busy ? "Evaluating…" : "Evaluate crop insights"}
          </Button>
        </Stack>
        {processRisks.error || processStage.error || processYield.error ? (
          <Alert severity="warning">
            One or more crop insight stages failed. Existing persisted results
            remain unchanged.
          </Alert>
        ) : null}
        <Divider />
        <Typography variant="caption" color="text.secondary">
          Risk signatures
        </Typography>
        {risks.isLoading ? (
          <Typography variant="caption">Loading risks…</Typography>
        ) : risks.data?.length ? (
          risks.data.map((risk) => (
            <Stack
              key={risk.id}
              spacing={0.5}
              sx={{ p: 1, border: 1, borderColor: "divider", borderRadius: 1 }}
            >
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                <Chip
                  size="small"
                  label={risk.issue_type.replaceAll("_", " ")}
                />
                <Chip
                  size="small"
                  label={risk.status}
                  color={risk.status === "candidate" ? "warning" : "default"}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Severity ${pct(risk.severity)}`}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Confidence ${pct(risk.confidence)}`}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Trend ${risk.trend}`}
                />
              </Stack>
              <Typography variant="caption">
                Factors: {JSON.stringify(risk.factors)} · evidence:{" "}
                {risk.evidence_ids.join(", ") || "none"}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Applicability:{" "}
                {String(
                  (risk.applicability.reasons as unknown[] | undefined)?.join(
                    ", ",
                  ) || "validated scope",
                )}
                . This is a suspected signature, not a confirmed disease.
              </Typography>
            </Stack>
          ))
        ) : (
          <Alert severity="info">
            No crop risk measured. Missing inputs or unvalidated crop models
            stay not measured.
          </Alert>
        )}
        <Divider />
        <Typography variant="caption" color="text.secondary">
          Growth and stage
        </Typography>
        {growth.data?.length ? (
          growth.data.map((metric) => (
            <Stack
              key={metric.id}
              direction={{ xs: "column", sm: "row" }}
              spacing={1}
            >
              <Chip
                size="small"
                label={`${metric.metric_kind}: ${metric.status}`}
                color={metric.status === "pass" ? "success" : "warning"}
              />
              <Typography variant="caption">
                {JSON.stringify(metric.summary)} ·{" "}
                {metric.units ?? "units unavailable"} · confidence{" "}
                {pct(metric.confidence)}
              </Typography>
            </Stack>
          ))
        ) : (
          <Typography variant="caption">
            Height/biomass not measured until calibrated stereo, LiDAR, or
            photogrammetry input is available.
          </Typography>
        )}
        {stage.data ? (
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              <Chip
                size="small"
                label={`Stage ${stage.data.predicted_stage ?? "not measured"}`}
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Status ${stage.data.status}`}
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Confidence ${pct(stage.data.confidence)}`}
              />
              {stage.data.human_stage ? (
                <Chip
                  size="small"
                  color="success"
                  label={`Human: ${stage.data.human_stage}`}
                />
              ) : null}
            </Stack>
            <Typography variant="caption">
              Candidates: {JSON.stringify(stage.data.candidates)} · evidence:{" "}
              {stage.data.evidence_ids.join(", ") || "none"}
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                size="small"
                label="Human growth stage"
                value={humanStage}
                onChange={(event) => setHumanStage(event.target.value)}
                inputProps={{ "aria-label": "Human growth stage correction" }}
              />
              <Button
                size="small"
                variant="outlined"
                disabled={!humanStage.trim() || correctStage.isPending}
                onClick={() =>
                  correctStage.mutate({
                    estimateId: stage.data.id,
                    payload: { human_stage: humanStage.trim() },
                  })
                }
              >
                Save correction
              </Button>
            </Stack>
          </Stack>
        ) : (
          <Typography variant="caption">
            Growth-stage estimate unavailable; field context may be shown as
            context-only.
          </Typography>
        )}
        <Divider />
        <Typography variant="caption" color="text.secondary">
          Yield forecast
        </Typography>
        {forecast.data ? (
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              <Chip
                size="small"
                label={
                  forecast.data.status === "pass"
                    ? "Range available"
                    : "Not applicable"
                }
                color={forecast.data.status === "pass" ? "success" : "warning"}
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Confidence ${pct(forecast.data.confidence)}`}
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Units ${forecast.data.units ?? "—"}`}
              />
            </Stack>
            <Typography variant="caption">
              Range: {JSON.stringify(forecast.data.forecast_range)} · interval:{" "}
              {JSON.stringify(forecast.data.confidence_interval)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Applicability:{" "}
              {String(
                (
                  forecast.data.applicability.reasons as unknown[] | undefined
                )?.join(", ") || "actual harvest history",
              )}
            </Typography>
          </Stack>
        ) : (
          <Typography variant="caption">
            Yield remains unavailable until multiple flights and quality
            actual-harvest labels exist.
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}
