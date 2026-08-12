import { PlayArrow } from "@mui/icons-material";
import {
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import type { VisionModelVersion } from "../visionTypes";

export function VisionModelRegistry({
  versions,
  onEvaluate,
}: {
  versions: VisionModelVersion[];
  onEvaluate: (version: VisionModelVersion) => void;
}) {
  return (
    <Grid container spacing={2}>
      {versions.map((version) => (
        <Grid key={version.id} size={{ xs: 12, md: 6, xl: 4 }}>
          <Card variant="outlined">
            <CardActionArea onClick={() => onEvaluate(version)}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="h6">
                    {version.name} v{version.version}
                  </Typography>
                  <Chip
                    size="small"
                    color={version.status === "production" ? "success" : "default"}
                    label={version.status}
                  />
                </Stack>
                <Typography color="text.secondary">
                  {version.crop} · {version.architecture}
                </Typography>
                <Stack direction="row" spacing={0.5} mt={2} flexWrap="wrap">
                  {version.classes.map((className) => (
                    <Chip key={className} size="small" label={className.replaceAll("_", " ")} />
                  ))}
                </Stack>
                <Button sx={{ mt: 2 }} startIcon={<PlayArrow />}>
                  View evaluation
                </Button>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}
