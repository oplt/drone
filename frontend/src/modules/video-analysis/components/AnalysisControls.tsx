import { Alert, List, ListItemButton, ListItemText, MenuItem, Slider, Stack, TextField, Typography } from "@mui/material";
import { ActionIconButton, ActionIconLabel } from "../../../shared/ui/ActionIconButton";
import { MODEL_OPTIONS } from "../modelOptions";
import type { AnalyzeVideoPayload, VideoAsset } from "../types";

const MAX_SIZE_BYTES = 1024 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = /\.(mp4|mov|avi|mkv|webm)$/i;

export type AnalysisControlsProps = {
  file: File | null;
  video: VideoAsset | null;
  payload: AnalyzeVideoPayload;
  uploading: boolean;
  starting: boolean;
  missionRecordings?: VideoAsset[];
  missionRecordingsLoading?: boolean;
  onSelectMissionRecording?: (recording: VideoAsset) => void;
  onFile: (file: File | null, error: string | null) => void;
  onPayload: (payload: AnalyzeVideoPayload) => void;
  onUpload: () => void;
  onAnalyze: () => void;
};

function formatRecordingTime(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return createdAt;
  return date.toLocaleString();
}

export function AnalysisSourceSection(props: AnalysisControlsProps) {
  const recordings = props.missionRecordings ?? [];
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
      <Typography variant="h6">Mission recordings</Typography>
      {props.missionRecordingsLoading ? (
        <Typography variant="body2" color="text.secondary">
          Loading mission recordings…
        </Typography>
      ) : recordings.length ? (
        <List dense disablePadding sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
          {recordings.map((recording) => (
            <ListItemButton
              key={recording.id}
              selected={props.video?.id === recording.id && !props.file}
              onClick={() => props.onSelectMissionRecording?.(recording)}
            >
              <ListItemText
                primary={recording.original_filename}
                secondary={`Recorded ${formatRecordingTime(recording.created_at)}`}
              />
            </ListItemButton>
          ))}
        </List>
      ) : (
        <Typography variant="body2" color="text.secondary">
          Flight recordings for this mission appear here after landing.
        </Typography>
      )}

      <Typography variant="h6" sx={{ pt: 1 }}>
        Upload video
      </Typography>
      <ActionIconLabel variant="upload" title="Select video">
        <input hidden type="file" accept="video/*" onChange={(event) => chooseFile(event.target.files?.[0])} />
      </ActionIconLabel>
      <Typography variant="body2" color="text.secondary">
        {props.file
          ? `${props.file.name} | ${(props.file.size / 1024 / 1024).toFixed(1)} MB`
          : "MP4, MOV, AVI, MKV or WEBM, up to 1 GB"}
      </Typography>
      {props.video ? (
        <Alert severity="success">
          {props.file ? "Upload ready for analysis." : "Mission recording selected for analysis."}
        </Alert>
      ) : null}
      <ActionIconButton
        variant="upload"
        title={
          props.uploading ? "Uploading…" : props.video ? "Replace upload" : "Upload video"
        }
        color="primary"
        loading={props.uploading}
        disabled={!props.file}
        onClick={props.onUpload}
      />
    </Stack>
  );
}

export function AnalysisInferenceSection(props: AnalysisControlsProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="h6">Detection profile</Typography>
      <TextField
        select
        size="small"
        label="Model"
        value={props.payload.model_name}
        onChange={(event) =>
          props.onPayload({
            ...props.payload,
            model_name: event.target.value as AnalyzeVideoPayload["model_name"],
          })
        }
      >
        {MODEL_OPTIONS.map((option) => (
          <MenuItem key={option.value} value={option.value}>
            {option.label}
          </MenuItem>
        ))}
      </TextField>
      <Typography variant="body2">
        Sampling interval: {props.payload.frame_stride_seconds.toFixed(1)} s
      </Typography>
      <Slider
        aria-label="Sampling interval seconds"
        min={0.2}
        max={5}
        step={0.1}
        value={props.payload.frame_stride_seconds}
        onChange={(_, value) =>
          props.onPayload({ ...props.payload, frame_stride_seconds: value as number })
        }
      />
      <Typography variant="body2">
        Minimum confidence: {(props.payload.confidence_threshold * 100).toFixed(0)}%
      </Typography>
      <Slider
        aria-label="Minimum confidence"
        min={0.05}
        max={0.95}
        step={0.05}
        value={props.payload.confidence_threshold}
        onChange={(_, value) =>
          props.onPayload({ ...props.payload, confidence_threshold: value as number })
        }
      />
      <ActionIconButton
        variant="play"
        title={props.starting ? "Queuing…" : "Run analysis"}
        color="secondary"
        loading={props.starting}
        disabled={!props.video}
        onClick={props.onAnalyze}
      />
    </Stack>
  );
}

export function AnalysisControls(props: AnalysisControlsProps) {
  return (
    <Stack spacing={2}>
      <AnalysisSourceSection {...props} />
      <AnalysisInferenceSection {...props} />
    </Stack>
  );
}
