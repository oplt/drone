import {
  Alert,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";
import {
  ActionIconButton,
  ActionIconLabel,
} from "../../../shared/ui/ActionIconButton";
import type { AnalysisControlsProps } from "./analysisControlsTypes";
import { CaptureMetadataEditor } from "./CaptureMetadataEditor";

const MAX_SIZE_BYTES = 1024 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = /\.(mp4|mov|avi|mkv|webm)$/i;

function formatRecordingTime(createdAt: string): string {
  const date = new Date(createdAt);
  return Number.isNaN(date.getTime()) ? createdAt : date.toLocaleString();
}

export function AnalysisSourceSection(props: AnalysisControlsProps) {
  const recordings = props.missionRecordings ?? [];
  const chooseFile = (selected: File | undefined) => {
    if (!selected) return props.onFile(null, null);
    if (selected.size > MAX_SIZE_BYTES)
      return props.onFile(null, "Video exceeds 1 GB upload limit.");
    if (!ACCEPTED_EXTENSIONS.test(selected.name))
      return props.onFile(null, "Use MP4, MOV, AVI, MKV, or WEBM video.");
    props.onFile(selected, null);
  };
  return (
    <Stack spacing={2}>
      <Typography variant="h6">Mission recordings</Typography>
      {props.missionRecordingsLoading ? (
        <Typography variant="body2" color="text.secondary">Loading mission recordings…</Typography>
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
      <Typography variant="h6" sx={{ pt: 1 }}>Upload video</Typography>
      <ActionIconLabel variant="upload" title="Select video">
        <input hidden type="file" accept="video/*" onChange={(event) => chooseFile(event.target.files?.[0])} />
      </ActionIconLabel>
      <Typography variant="body2" color="text.secondary">
        {props.file ? `${props.file.name} | ${(props.file.size / 1024 / 1024).toFixed(1)} MB` : "MP4, MOV, AVI, MKV or WEBM, up to 1 GB"}
      </Typography>
      {props.video ? (
        <Alert severity="success">{props.file ? "Upload ready for analysis." : "Mission recording selected for analysis."}</Alert>
      ) : null}
      <ActionIconButton
        variant="upload"
        title={props.uploading ? "Uploading…" : props.video ? "Replace upload" : "Upload video"}
        color="primary"
        loading={props.uploading}
        disabled={!props.file}
        onClick={props.onUpload}
      />
      {props.video && !props.file ? (
        <CaptureMetadataEditor
          video={props.video}
          onUpdated={props.onVideoUpdated}
        />
      ) : null}
    </Stack>
  );
}
