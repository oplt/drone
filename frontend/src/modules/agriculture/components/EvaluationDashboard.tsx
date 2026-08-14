import { useMemo, useState } from "react";
import { RocketLaunch } from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  Chip,
  Grid,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import {
  useDeployModelVersion,
  useModelEvaluation,
} from "../hooks/useVisionModels";
import type { VisionModelVersion } from "../visionTypes";
import { metricSummary } from "../evaluationDisplay";
import { EvaluationComparison } from "./EvaluationComparison";
import { EvaluationDeployDialog } from "./EvaluationDeployDialog";
import { EvaluationDetails } from "./EvaluationDetails";
import { EvaluationMetricsPanel } from "./EvaluationMetricsPanel";

export function EvaluationDashboard({
  version,
  allVersions,
}: {
  version: VisionModelVersion;
  allVersions: VisionModelVersion[];
}) {
  const evaluation = useModelEvaluation(version.id);
  const deploy = useDeployModelVersion();
  const siblings = allVersions.filter(
    (item) => item.model_id === version.model_id && item.id !== version.id,
  );
  const currentProduction = siblings.find((item) => item.status === "production");
  const [comparisonId, setComparisonId] = useState(
    () => currentProduction?.id ?? "",
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const artifactByName = useMemo(
    () => new Map(evaluation.data?.artifacts.map((artifact) => [artifact.name, artifact])),
    [evaluation.data?.artifacts],
  );
  if (evaluation.isLoading) {
    return (
      <Grid container spacing={2}>
        {[1, 2, 3, 4].map((item) => (
          <Grid key={item} size={{ xs: 12, sm: 6, lg: 3 }}>
            <Skeleton variant="rounded" height={118} />
          </Grid>
        ))}
        <Grid size={{ xs: 12 }}><Skeleton variant="rounded" height={320} /></Grid>
      </Grid>
    );
  }
  if (evaluation.error || !evaluation.data)
    return <Alert severity="error">Model evaluation failed to load: {evaluation.error?.message}</Alert>;
  const data = evaluation.data;
  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
        <Box>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="h5">{data.model_name} v{data.version}</Typography>
            <Chip size="small" color={version.status === "production" ? "success" : "default"} label={version.status} />
            {currentProduction && version.id !== currentProduction.id ? (
              <Chip size="small" variant="outlined" color="success" label={`Production: v${currentProduction.version}`} />
            ) : null}
          </Stack>
          <Typography color="text.secondary">
            Test split · {data.test_image_count} images · Dataset v{data.dataset_version}
          </Typography>
        </Box>
        {version.status !== "production" && version.status !== "archived" ? (
          <Button variant="contained" startIcon={<RocketLaunch />} onClick={() => setConfirmOpen(true)}>
            Deploy candidate
          </Button>
        ) : null}
      </Stack>
      <EvaluationMetricsPanel
        data={data}
        artifacts={artifactByName}
        baselineSummary={
          currentProduction && version.id !== currentProduction.id
            ? metricSummary(currentProduction)
            : undefined
        }
        baselineLabel={
          currentProduction && version.id !== currentProduction.id
            ? `production v${currentProduction.version}`
            : undefined
        }
      />
      <EvaluationDetails data={data} />
      <EvaluationComparison
        siblings={siblings}
        current={data.summary}
        comparisonId={comparisonId}
        setComparisonId={setComparisonId}
        productionVersionId={currentProduction?.id}
      />
      <EvaluationDeployDialog
        open={confirmOpen}
        version={version}
        evaluation={data}
        currentProduction={currentProduction}
        pending={deploy.isPending}
        close={() => setConfirmOpen(false)}
        confirm={() => void deploy.mutateAsync(version.id).then(() => setConfirmOpen(false))}
      />
    </Stack>
  );
}
