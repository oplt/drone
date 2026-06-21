import { useMemo, useState } from "react";
import { Alert, Box, Container, Grid, Stack, Typography } from "@mui/material";
import { AnalysisWorkflowTabs } from "./components/AnalysisWorkflowTabs";
import { DetectionLogsTabs } from "./components/DetectionLogsTabs";
import { DetectionMap } from "./components/DetectionMap";
import { DetectionTimeline } from "./components/DetectionTimeline";
import { VideoOverlayPlayer } from "./components/VideoOverlayPlayer";
import {
  useAnalysisJob,
  useDetections,
  useLiveSavedDetections,
  useStartAnalysis,
  useUploadVideo,
} from "./hooks";
import { DEFAULT_MODEL } from "./modelOptions";
import type { AnalyzeVideoPayload, VideoAsset, VideoDetection } from "./types";

const DEFAULT_PAYLOAD: AnalyzeVideoPayload = {
  model_name: DEFAULT_MODEL,
  frame_stride_seconds: 1,
  confidence_threshold: 0.35,
};

export default function VideoAnalysisPage() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [video, setVideo] = useState<VideoAsset | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [selected, setSelected] = useState<VideoDetection | null>(null);
  const [durationSeconds, setDurationSeconds] = useState(1);
  const [payload, setPayload] = useState<AnalyzeVideoPayload>(DEFAULT_PAYLOAD);
  const upload = useUploadVideo();
  const start = useStartAnalysis();
  const job = useAnalysisJob(jobId);
  const detections = useDetections(jobId, job.data?.status);
  const liveDetections = useLiveSavedDetections();
  const rows = useMemo(() => detections.data ?? [], [detections.data]);
  const topLabels = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((detection) => counts.set(detection.label, (counts.get(detection.label) ?? 0) + 1));
    return [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 5);
  }, [rows]);
  const error = fileError ?? [upload.error, start.error, job.error, detections.error].find(Boolean)?.message;

  const chooseFile = (next: File | null, validationError: string | null) => {
    setFile(next);
    setFileError(validationError);
    setVideo(null);
    setJobId(null);
    setSelected(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    const uploaded = await upload.mutateAsync(file);
    setVideo(uploaded);
  };

  const handleAnalyze = async () => {
    if (!video) return;
    const created = await start.mutateAsync({ videoId: video.id, payload });
    setJobId(created.id);
    setSelected(null);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="overline" color="primary">Offline intelligence</Typography>
          <Typography variant="h4" fontWeight={700}>Drone video analysis</Typography>
          <Typography color="text.secondary">Sample recorded footage, detect targets, inspect evidence by time and location.</Typography>
        </Box>
        {error ? <Alert severity="error">{error}</Alert> : null}
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 3 }}>
            <AnalysisWorkflowTabs
              file={file}
              video={video}
              payload={payload}
              uploading={upload.isPending}
              starting={start.isPending}
              onFile={chooseFile}
              onPayload={setPayload}
              onUpload={handleUpload}
              onAnalyze={handleAnalyze}
              job={job.data}
              detectionCount={rows.length}
            />
          </Grid>
          <Grid size={{ xs: 12, lg: 6 }}>
            <Stack spacing={2}>
              <VideoOverlayPlayer file={file} detections={rows} selected={selected} onDurationChange={setDurationSeconds} />
              <DetectionTimeline detections={rows} selected={selected} durationSeconds={durationSeconds} status={job.data?.status} onSelect={setSelected} />
              {topLabels.length ? <Alert severity="info">Frequent detections: {topLabels.map(([label, count]) => `${label}: ${count}`).join(" | ")}</Alert> : null}
            </Stack>
          </Grid>
          <Grid size={{ xs: 12, lg: 3 }}>
            <DetectionMap detections={rows} selected={selected} onSelect={setSelected} />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <DetectionLogsTabs
              liveRows={liveDetections.data ?? []}
              liveLoading={liveDetections.isLoading}
              jobRows={rows}
              jobLoading={detections.isLoading}
              onJobRowSelect={setSelected}
            />
          </Grid>
        </Grid>
      </Stack>
    </Container>
  );
}
