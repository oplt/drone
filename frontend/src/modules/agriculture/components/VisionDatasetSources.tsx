import { useState } from "react";
import { CloudUpload, Videocam } from "@mui/icons-material";
import {
  Alert,
  Button,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMissionVideos } from "../../video-analysis/hooks";
import {
  useExtractVisionFrames,
  useUploadVisionImages,
} from "../hooks/useVisionModels";

export function VisionImageUploadCard({ datasetId }: { datasetId: string }) {
  const upload = useUploadVisionImages(datasetId);
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6">Upload images</Typography>
          <Typography color="text.secondary">
            JPEG, PNG, TIFF, or WebP. Images are normalized, thumbnailed, and
            deduplicated.
          </Typography>
          <Button
            component="label"
            variant="outlined"
            startIcon={<CloudUpload />}
            disabled={upload.isPending}
          >
            Choose images
            <input
              hidden
              multiple
              type="file"
              accept="image/jpeg,image/png,image/tiff,image/webp"
              onChange={(event) => {
                const files = [...(event.target.files ?? [])];
                if (files.length) upload.mutate(files);
                event.target.value = "";
              }}
            />
          </Button>
          {upload.data ? (
            <Alert severity="success">
              Added {upload.data.added}; skipped {upload.data.duplicates} duplicates.
              {upload.data.rejected.length
                ? ` ${upload.data.rejected.length} quality warnings.`
                : ""}
            </Alert>
          ) : null}
          {upload.error ? <Alert severity="error">{upload.error.message}</Alert> : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function VisionVideoCurationCard({ datasetId }: { datasetId: string }) {
  const extract = useExtractVisionFrames(datasetId);
  const missionVideos = useMissionVideos(null, null, { enabled: true });
  const [videoId, setVideoId] = useState("");
  const [interval, setInterval] = useState(1);
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6">Curate mission video</Typography>
          <FormControl size="small" fullWidth>
            <InputLabel>Mission recording</InputLabel>
            <Select
              label="Mission recording"
              value={videoId}
              onChange={(event) => setVideoId(event.target.value)}
            >
              {missionVideos.data?.map((video) => (
                <MenuItem key={video.id} value={video.id}>
                  {video.original_filename}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            type="number"
            label="Frame interval (seconds)"
            value={interval}
            slotProps={{ htmlInput: { min: 0.2, max: 30, step: 0.1 } }}
            onChange={(event) => setInterval(Number(event.target.value))}
          />
          <Button
            variant="outlined"
            startIcon={<Videocam />}
            disabled={!videoId || extract.isPending}
            onClick={() =>
              extract.mutate({ video_id: videoId, interval_seconds: interval })
            }
          >
            Curate frames
          </Button>
          {extract.data ? (
            <Alert severity="success">
              Selected {extract.data.selected_frames} of {extract.data.candidate_frames}
              {" candidates; rejected "}
              {extract.data.rejected_quality} quality and{" "}
              {extract.data.rejected_duplicates} duplicate frames.
            </Alert>
          ) : null}
          {extract.error ? <Alert severity="error">{extract.error.message}</Alert> : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
