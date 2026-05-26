import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Alert, Button, Card, CardContent, MenuItem, Slider, Stack, TextField, Typography } from "@mui/material";
import { MODEL_OPTIONS } from "../modelOptions";
import type { AnalyzeVideoPayload, VideoAsset } from "../types";

const MAX_SIZE_BYTES = 1024 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = /\.(mp4|mov|avi|mkv|webm)$/i;

type Props = {
  file: File | null;
  video: VideoAsset | null;
  payload: AnalyzeVideoPayload;
  uploading: boolean;
  starting: boolean;
  onFile: (file: File | null, error: string | null) => void;
  onPayload: (payload: AnalyzeVideoPayload) => void;
  onUpload: () => void;
  onAnalyze: () => void;
};

export function AnalysisControls(props: Props) {
  const chooseFile = (selected: File | undefined) => {
    if (!selected) return props.onFile(null, null);
    if (selected.size > MAX_SIZE_BYTES) return props.onFile(null, "Video exceeds 1 GB upload limit.");
    if (!ACCEPTED_EXTENSIONS.test(selected.name)) {
      return props.onFile(null, "Use MP4, MOV, AVI, MKV, or WEBM video.");
    }
    props.onFile(selected, null);
  };

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="overline" color="text.secondary">01 / Source</Typography>
            <Typography variant="h6">Flight recording</Typography>
            <Button component="label" variant="outlined" startIcon={<CloudUploadIcon />}>
              Select video
              <input hidden type="file" accept="video/*" onChange={(event) => chooseFile(event.target.files?.[0])} />
            </Button>
            <Typography variant="body2" color="text.secondary">
              {props.file ? `${props.file.name} | ${(props.file.size / 1024 / 1024).toFixed(1)} MB` : "MP4, MOV, AVI, MKV or WEBM, up to 1 GB"}
            </Typography>
            {props.video ? <Alert severity="success">Upload ready for analysis.</Alert> : null}
            <Button variant="contained" disabled={!props.file || props.uploading} onClick={props.onUpload}>
              {props.uploading ? "Uploading..." : props.video ? "Replace upload" : "Upload video"}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="overline" color="text.secondary">02 / Inference</Typography>
            <Typography variant="h6">Detection profile</Typography>
            <TextField
              select
              size="small"
              label="Model"
              value={props.payload.model_name}
              onChange={(event) => props.onPayload({ ...props.payload, model_name: event.target.value as AnalyzeVideoPayload["model_name"] })}
            >
              {MODEL_OPTIONS.map((option) => (
                <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
              ))}
            </TextField>
            <Typography variant="body2">Sampling interval: {props.payload.frame_stride_seconds.toFixed(1)} s</Typography>
            <Slider aria-label="Sampling interval seconds" min={0.2} max={5} step={0.1} value={props.payload.frame_stride_seconds} onChange={(_, value) => props.onPayload({ ...props.payload, frame_stride_seconds: value as number })} />
            <Typography variant="body2">Minimum confidence: {(props.payload.confidence_threshold * 100).toFixed(0)}%</Typography>
            <Slider aria-label="Minimum confidence" min={0.05} max={0.95} step={0.05} value={props.payload.confidence_threshold} onChange={(_, value) => props.onPayload({ ...props.payload, confidence_threshold: value as number })} />
            <Button variant="contained" color="secondary" disabled={!props.video || props.starting} startIcon={<PlayArrowIcon />} onClick={props.onAnalyze}>
              {props.starting ? "Queuing..." : "Run analysis"}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
