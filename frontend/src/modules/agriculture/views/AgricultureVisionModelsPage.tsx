import { useMemo, useState } from "react";
import { Add } from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { EvaluationDashboard } from "../components/EvaluationDashboard";
import { VisionDatasetWorkspace } from "../components/VisionDatasetWorkspace";
import { VisionModelRegistry } from "../components/VisionModelRegistry";
import { VisionProjectCreateDialog } from "../components/VisionProjectCreateDialog";
import { VisionTrainingWorkspace } from "../components/VisionTrainingWorkspace";
import {
  useVisionDatasets,
  useVisionModels,
  useVisionProjects,
} from "../hooks/useVisionModels";
import type { VisionModelVersion } from "../visionTypes";

type WorkspaceTab = "dataset" | "train" | "evaluation" | "models";

export default function AgricultureVisionModelsPage() {
  const projects = useVisionProjects();
  const models = useVisionModels();
  const [createOpen, setCreateOpen] = useState(false);
  const [requestedProjectId, setRequestedProjectId] = useState<string | null>(null);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [tab, setTab] = useState<WorkspaceTab>("dataset");
  const [evaluationVersion, setEvaluationVersion] =
    useState<VisionModelVersion | null>(null);
  const projectId = projects.data?.some((item) => item.id === requestedProjectId)
    ? requestedProjectId
    : projects.data?.[0]?.id ?? null;
  const datasets = useVisionDatasets(projectId);
  const project = projects.data?.find((item) => item.id === projectId) ?? null;
  const latestDataset = useMemo(
    () =>
      datasets.data?.find((item) => item.id === datasetId) ??
      datasets.data?.[0] ??
      null,
    [datasetId, datasets.data],
  );
  const projectModels =
    models.data?.filter((item) => item.project_id === projectId) ?? [];

  const chooseEvaluation = (version: VisionModelVersion) => {
    setEvaluationVersion(version);
    setTab("evaluation");
  };
  if (projects.isLoading)
    return <CircularProgress aria-label="Loading vision projects" />;
  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="overline" color="primary">Agriculture intelligence</Typography>
          <Typography variant="h4" fontWeight={700}>Vision models</Typography>
          <Typography color="text.secondary">
            Curate imagery, label objects, train, evaluate, and deploy crop-specific detectors.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
          New project
        </Button>
      </Stack>
      {!projects.data?.length ? (
        <Card variant="outlined">
          <CardContent>
            <Stack alignItems="flex-start" spacing={2}>
              <Typography variant="h6">No vision projects yet</Typography>
              <Typography color="text.secondary">Start with a crop and its object classes.</Typography>
              <Button variant="contained" onClick={() => setCreateOpen(true)}>Create first project</Button>
            </Stack>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, lg: 3 }}>
            <Stack spacing={1}>
              {projects.data.map((item) => (
                <Card key={item.id} variant={item.id === projectId ? "elevation" : "outlined"}>
                  <CardActionArea onClick={() => {
                    setRequestedProjectId(item.id);
                    setDatasetId(null);
                    setEvaluationVersion(null);
                    setTab("dataset");
                  }}>
                    <CardContent>
                      <Typography fontWeight={700}>{item.name}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {item.crop} · {item.classes.length} classes
                      </Typography>
                      <Stack direction="row" spacing={1} mt={1}>
                        <Chip size="small" label={`${item.dataset_count} datasets`} />
                        {item.production_model_version ? (
                          <Chip size="small" color="success" label={`v${item.production_model_version} production`} />
                        ) : null}
                      </Stack>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
            </Stack>
          </Grid>
          <Grid size={{ xs: 12, lg: 9 }}>
            {project ? (
              <Stack spacing={2}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                  <Box>
                    <Typography variant="h5">{project.name}</Typography>
                    <Typography color="text.secondary">
                      {project.crop} · {project.classes.map((item) => item.name.replaceAll("_", " ")).join(", ")}
                    </Typography>
                  </Box>
                  {datasets.data?.length ? (
                    <FormControl size="small" sx={{ minWidth: 170 }}>
                      <InputLabel>Dataset</InputLabel>
                      <Select value={latestDataset?.id ?? ""} label="Dataset" onChange={(event) => setDatasetId(event.target.value)}>
                        {datasets.data.map((item) => (
                          <MenuItem key={item.id} value={item.id}>Dataset v{item.version} · {item.status}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  ) : null}
                </Stack>
                <Divider />
                <Tabs value={tab} onChange={(_, value: WorkspaceTab) => setTab(value)} variant="scrollable">
                  <Tab value="dataset" label="Dataset & labels" />
                  <Tab value="train" label="Train" />
                  <Tab value="evaluation" label="Evaluation" />
                  <Tab value="models" label="Model registry" />
                </Tabs>
                <Box pt={1}>
                  {tab === "dataset" ? <VisionDatasetWorkspace projectId={project.id} dataset={latestDataset} /> : null}
                  {tab === "train" ? <VisionTrainingWorkspace projectId={project.id} dataset={latestDataset} /> : null}
                  {tab === "models" ? <VisionModelRegistry versions={projectModels} onEvaluate={chooseEvaluation} /> : null}
                  {tab === "evaluation" && evaluationVersion ? (
                    <EvaluationDashboard version={evaluationVersion} allVersions={projectModels} />
                  ) : null}
                  {tab === "evaluation" && !evaluationVersion && projectModels.length ? (
                    <VisionModelRegistry versions={projectModels} onEvaluate={setEvaluationVersion} />
                  ) : null}
                  {tab === "evaluation" && !projectModels.length ? (
                    <Alert severity="info">Complete training to generate real test-set metrics.</Alert>
                  ) : null}
                </Box>
              </Stack>
            ) : null}
          </Grid>
        </Grid>
      )}
      <VisionProjectCreateDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Stack>
  );
}
