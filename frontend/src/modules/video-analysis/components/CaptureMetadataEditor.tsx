import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import type { VideoAsset } from "../types";
import { usePatchCaptureMetadata } from "../hooks";

type Props = {
  video: VideoAsset | null;
  onUpdated?: (video: VideoAsset) => void;
};

function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function CaptureMetadataEditor({ video, onUpdated }: Props) {
  const patch = usePatchCaptureMetadata();
  const [capturedAt, setCapturedAt] = useState("");
  const [timezone, setTimezone] = useState("");
  const [syncOffset, setSyncOffset] = useState("0");

  useEffect(() => {
    if (!video) {
      setCapturedAt("");
      setTimezone("");
      setSyncOffset("0");
      return;
    }
    setCapturedAt(toLocalInputValue(video.captured_at));
    setTimezone(video.capture_timezone ?? "");
    setSyncOffset(String(video.sync_offset_seconds ?? 0));
  }, [video]);

  if (!video) return null;

  const save = async () => {
    const body: {
      captured_at?: string;
      capture_timezone?: string;
      sync_offset_seconds?: number;
    } = {};
    if (capturedAt.trim()) {
      body.captured_at = new Date(capturedAt).toISOString();
    }
    if (timezone.trim()) body.capture_timezone = timezone.trim();
    const offset = Number(syncOffset);
    if (Number.isFinite(offset)) body.sync_offset_seconds = offset;
    if (
      body.captured_at == null &&
      body.capture_timezone == null &&
      body.sync_offset_seconds == null
    ) {
      return;
    }
    const updated = await patch.mutateAsync({ videoId: video.id, patch: body });
    onUpdated?.(updated);
  };

  return (
    <Stack spacing={1.5} sx={{ mt: 2 }}>
      <Typography variant="subtitle2">Capture time (operator)</Typography>
      <Typography variant="body2" color="text.secondary">
        Correct upload-time fallbacks before re-running analysis. Saving sets
        source to operator and flags reanalysis when values change.
      </Typography>
      <TextField
        size="small"
        label="Captured at"
        type="datetime-local"
        value={capturedAt}
        onChange={(event) => setCapturedAt(event.target.value)}
        InputLabelProps={{ shrink: true }}
        inputProps={{ "aria-label": "Captured at local time" }}
      />
      <TextField
        size="small"
        label="Timezone"
        placeholder="UTC or Europe/Berlin"
        value={timezone}
        onChange={(event) => setTimezone(event.target.value)}
      />
      <TextField
        size="small"
        label="Sync offset (seconds)"
        type="number"
        value={syncOffset}
        onChange={(event) => setSyncOffset(event.target.value)}
        inputProps={{ step: 0.1, min: -3600, max: 3600 }}
      />
      {patch.error ? (
        <Alert severity="error">{patch.error.message}</Alert>
      ) : null}
      <Button
        variant="outlined"
        size="small"
        disabled={patch.isPending}
        onClick={() => void save()}
        sx={{ minHeight: 44, alignSelf: "flex-start" }}
      >
        {patch.isPending ? "Saving…" : "Save capture metadata"}
      </Button>
    </Stack>
  );
}
