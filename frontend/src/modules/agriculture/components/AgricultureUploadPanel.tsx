import { Alert, Button, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAgricultureMediaUpload } from "../uploadWorkflow";

export function AgricultureUploadPanel({ flightId }: { flightId: string }) {
  const [fileName, setFileName] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const upload = useAgricultureMediaUpload(flightId);
  return (
    <Paper component="section" aria-labelledby="agriculture-upload-heading" variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography id="agriculture-upload-heading" variant="subtitle2">Capture upload</Typography>
        <Typography variant="caption" color="text.secondary">Uploads resume from the last confirmed chunk after refresh or reconnect.</Typography>
        <input type="file" accept="image/*,video/*" aria-label="Select agriculture media" onChange={(event) => { const selected = event.target.files?.[0] ?? null; setFile(selected); setFileName(selected?.name ?? null); }} />
        {fileName ? <Typography variant="caption">Selected: {fileName}</Typography> : null}
        <Button variant="outlined" size="small" disabled={!file || upload.isPending} onClick={() => file && upload.mutate(file)}>
          {upload.isPending ? "Uploading…" : "Upload media"}
        </Button>
        {upload.isPending ? <LinearProgress aria-label="Media upload in progress" /> : null}
        {upload.isError ? <Alert severity="error">Upload paused or quarantined after validation. Select the same file and retry; confirmed chunks are retained. Check the media inventory for the persisted security state.</Alert> : null}
        {upload.isSuccess ? <Alert severity="success">Media uploaded and checksum verified.</Alert> : null}
      </Stack>
    </Paper>
  );
}
