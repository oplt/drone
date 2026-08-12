import { Add, Dataset, EditNote } from "@mui/icons-material";
import {
  Box,
  Button,
  Card,
  CardContent,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import {
  useCreateVisionDataset,
  useVisionImages,
} from "../hooks/useVisionModels";
import type { VisionDataset } from "../visionTypes";
import {
  VisionImageUploadCard,
  VisionVideoCurationCard,
} from "./VisionDatasetSources";

export function VisionDatasetWorkspace({
  projectId,
  dataset,
}: {
  projectId: string;
  dataset: VisionDataset | null;
}) {
  const navigate = useNavigate();
  const createDataset = useCreateVisionDataset();
  const images = useVisionImages(dataset?.id ?? null);
  if (!dataset) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Stack alignItems="flex-start" spacing={2}>
            <Dataset color="action" fontSize="large" />
            <Typography variant="h6">Start dataset v1</Typography>
            <Typography color="text.secondary">
              Upload drone images or curate frames from mission recordings.
              Duplicate and low-quality frames are screened automatically.
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              disabled={createDataset.isPending}
              onClick={() => createDataset.mutate(projectId)}
            >
              Create dataset
            </Button>
          </Stack>
        </CardContent>
      </Card>
    );
  }
  const stats = [
    { label: "Total", value: dataset.image_count },
    { label: "Selected", value: dataset.selected_count },
    { label: "Reviewed", value: dataset.reviewed_count },
    {
      label: "Labeled, unreviewed",
      value: Math.max(0, dataset.labeled_count - dataset.reviewed_count),
    },
    { label: "Unlabeled", value: Math.max(0, dataset.image_count - dataset.labeled_count) },
  ];
  return (
    <Stack spacing={3}>
      <Grid container spacing={2}>
        {stats.map((stat) => (
          <Grid key={stat.label} size={{ xs: 6, md: "grow" }}>
            <Card variant="outlined">
              <CardContent>
                <Typography color="text.secondary" variant="body2">
                  {stat.label}
                </Typography>
                <Typography variant="h4">{stat.value}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 6 }}>
          <VisionImageUploadCard datasetId={dataset.id} />
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <VisionVideoCurationCard datasetId={dataset.id} />
        </Grid>
      </Grid>
      <Card variant="outlined">
        <CardContent>
          <Stack
            direction={{ xs: "column", md: "row" }}
            justifyContent="space-between"
            alignItems={{ md: "center" }}
            spacing={2}
          >
            <Box>
              <Typography variant="h6">Labeling readiness</Typography>
              <Typography color="text.secondary">
                {images.data?.total ?? dataset.image_count} curated images ·
                negative images can be reviewed with zero boxes.
              </Typography>
            </Box>
            <Button
              variant="contained"
              startIcon={<EditNote />}
              disabled={!dataset.image_count}
              onClick={() =>
                navigate(
                  `/dashboard/agriculture/vision-models/datasets/${dataset.id}/label`,
                )
              }
            >
              Open labeling workspace
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
