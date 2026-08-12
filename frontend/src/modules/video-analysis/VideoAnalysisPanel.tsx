import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Divider,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { AnalysisWorkflowTabs } from "./components/AnalysisWorkflowTabs";
import { DetectionLogsTabs } from "./components/DetectionLogsTabs";
import { DetectionMap } from "./components/DetectionMap";
import { DetectionTimeline } from "./components/DetectionTimeline";
import { VideoOverlayPlayer } from "./components/VideoOverlayPlayer";
import { buildMissionVideoStreamUrl } from "./api";
import { selectedDetectionEvidence } from "./evidenceSelection";
import {
  useAnalysisJob,
  useAnalysisSummary,
  useCancelAnalysis,
  useDetections,
  useLiveSavedDetections,
  useMissionVideos,
  useStartAnalysis,
  useUploadVideo,
} from "./hooks";
import { DEFAULT_MODEL } from "./modelOptions";
import type { AnalyzeVideoPayload, VideoAsset, VideoDetection } from "./types";

const DEFAULT_PAYLOAD: AnalyzeVideoPayload = {
  model_name: DEFAULT_MODEL,
  frame_stride_seconds: 1,
  confidence_threshold: 0.35,
  model_version_id: null,
  tracking_enabled: false,
  tracker_type: "bytetrack",
  small_object_mode: false,
};

type VideoAnalysisPanelProps = {
  embedded?: boolean;
  missionId?: string | null;
  fieldId?: number | null;
  flightActive?: boolean;
  agricultureMode?: boolean;
};

export function VideoAnalysisPanel({
  embedded = false,
  missionId = null,
  fieldId = null,
  flightActive = false,
  agricultureMode = false,
}: VideoAnalysisPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [video, setVideo] = useState<VideoAsset | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [selected, setSelected] = useState<VideoDetection | null>(null);
  const [durationSeconds, setDurationSeconds] = useState(1);
  const [payload, setPayload] = useState<AnalyzeVideoPayload>(DEFAULT_PAYLOAD);
  const [requestedEvidenceId, setRequestedEvidenceId] = useState<string | null>(
    null,
  );

  const queryMissionId = missionId;
  const missionVideos = useMissionVideos(queryMissionId, fieldId, {
    flightActive,
  });
  const refetchMissionVideos = missionVideos.refetch;
  const upload = useUploadVideo();
  const start = useStartAnalysis();
  const job = useAnalysisJob(jobId);
  const detections = useDetections(jobId, job.data?.status);
  const summary = useAnalysisSummary(jobId, job.data?.status);
  const cancel = useCancelAnalysis();
  const liveDetections = useLiveSavedDetections();
  const playbackUrl = useMemo(
    () =>
      video && !file ? buildMissionVideoStreamUrl(video.id) : null,
    [file, video],
  );

  const rows = useMemo(
    () => detections.data?.items ?? [],
    [detections.data?.items],
  );
  const topLabels = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((detection) =>
      counts.set(detection.label, (counts.get(detection.label) ?? 0) + 1),
    );
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5);
  }, [rows]);
  const error =
    fileError ??
    [
      upload.error,
      start.error,
      job.error,
      detections.error,
      missionVideos.error,
    ].find(Boolean)?.message;

  useEffect(() => {
    if (!flightActive && queryMissionId) {
      void refetchMissionVideos();
    }
  }, [flightActive, queryMissionId, refetchMissionVideos]);

  useEffect(() => {
    performance.mark("video-analysis-panel-open");
    return () => {
      performance.mark("video-analysis-panel-close");
      performance.measure(
        "video-analysis-panel-visible",
        "video-analysis-panel-open",
        "video-analysis-panel-close",
      );
    };
  }, []);

  useEffect(() => {
    const syncFromUrl = () => setRequestedEvidenceId(selectedDetectionEvidence());
    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);
    return () => {
      window.removeEventListener("popstate", syncFromUrl);
    };
  }, []);

  useEffect(() => {
    if (!requestedEvidenceId) return;
    const match = rows.find((row) => row.id === requestedEvidenceId);
    if (match) {
      setSelected(match);
      setRequestedEvidenceId(null);
    }
  }, [requestedEvidenceId, rows]);

  useEffect(() => {
    const recordings = missionVideos.data ?? [];
    if (!recordings.length || video || file) return;
    setVideo(recordings[0]);
  }, [file, missionVideos.data, video]);

  const chooseFile = (next: File | null, validationError: string | null) => {
    setFile(next);
    setFileError(validationError);
    setVideo(null);
    setJobId(null);
    setSelected(null);
  };

  const selectMissionRecording = (recording: VideoAsset) => {
    setFile(null);
    setFileError(null);
    setVideo(recording);
    setJobId(null);
    setSelected(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    const uploaded = await upload.mutateAsync({
      file,
      missionId: queryMissionId,
      fieldId,
    });
    setVideo(uploaded);
    void missionVideos.refetch();
  };

  const handleAnalyze = async () => {
    if (!video) return;
    const created = await start.mutateAsync({ videoId: video.id, payload });
    setJobId(created.id);
    setSelected(null);
  };

  return (
    <Stack spacing={2} sx={{ pt: embedded ? 0.5 : 0 }}>
      {!embedded ? (
        <Box>
          <Typography variant="overline" color="primary">
            Offline intelligence
          </Typography>
          <Typography variant="h4" fontWeight={700}>
            {agricultureMode
              ? "Agriculture evidence review"
              : "Drone video analysis"}
          </Typography>
          <Typography color="text.secondary">
            {agricultureMode
              ? "Review field-health evidence, quality, detections, and georeferenced issue context."
              : "Sample recorded footage, detect targets, inspect evidence by time and location."}
          </Typography>
        </Box>
      ) : null}

      {error ? <Alert severity="error">{error}</Alert> : null}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: embedded ? 12 : 3, xl: embedded ? 4 : 3 }}>
          <AnalysisWorkflowTabs
            file={file}
            video={video}
            payload={payload}
            uploading={upload.isPending}
            starting={start.isPending}
            missionRecordings={missionVideos.data ?? []}
            missionRecordingsLoading={
              missionVideos.isLoading || missionVideos.isFetching
            }
            onSelectMissionRecording={selectMissionRecording}
            onFile={chooseFile}
            onPayload={setPayload}
            onUpload={handleUpload}
            onAnalyze={handleAnalyze}
            job={job.data}
            detectionCount={rows.length}
            cancelling={cancel.isPending}
            onCancel={jobId ? () => cancel.mutate(jobId) : undefined}
          />
        </Grid>
        <Grid size={{ xs: 12, lg: embedded ? 12 : 6, xl: embedded ? 8 : 6 }}>
          <Stack spacing={2}>
            <VideoOverlayPlayer
              file={file}
              playbackUrl={playbackUrl}
              detections={rows}
              selected={selected}
              onDurationChange={setDurationSeconds}
            />
            <DetectionTimeline
              detections={rows}
              selected={selected}
              durationSeconds={durationSeconds}
              status={job.data?.status}
              onSelect={setSelected}
            />
            {topLabels.length ? (
              <Alert severity="info">
                Frequent detections:{" "}
                {topLabels
                  .map(([label, count]) => `${label}: ${count}`)
                  .join(" | ")}
              </Alert>
            ) : null}
            {summary.data ? (
              <Card variant="outlined">
                <CardContent>
                  <Stack spacing={1.5}>
                    <Typography variant="h6">
                      {summary.data.registered_model?.crop ?? "Object"} analysis
                    </Typography>
                    {summary.data.tracking_enabled ? (
                      <Box>
                        <Typography variant="subtitle2">
                          Unique tracked objects
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Estimated from tracker continuity; camera motion and
                          sampling affect counts.
                        </Typography>
                        {Object.entries(
                          summary.data.unique_tracked_objects_by_class,
                        ).map(([label, count]) => (
                          <Stack
                            key={label}
                            direction="row"
                            justifyContent="space-between"
                          >
                            <Typography>
                              {label.replaceAll("_", " ")}
                            </Typography>
                            <Typography fontWeight={700}>
                              {count.toLocaleString()}
                            </Typography>
                          </Stack>
                        ))}
                      </Box>
                    ) : null}
                    <Divider />
                    <Box>
                      <Typography variant="subtitle2">
                        Frame detections
                      </Typography>
                      {Object.entries(summary.data.detections_by_class).map(
                        ([label, count]) => (
                          <Stack
                            key={label}
                            direction="row"
                            justifyContent="space-between"
                          >
                            <Typography>
                              {label.replaceAll("_", " ")}
                            </Typography>
                            <Typography fontWeight={700}>
                              {count.toLocaleString()}
                            </Typography>
                          </Stack>
                        ),
                      )}
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      Model: {summary.data.model_name} · Tracking{" "}
                      {summary.data.tracking_enabled ? "enabled" : "off"} ·
                      Small-object mode{" "}
                      {summary.data.small_object_mode ? "enabled" : "off"}
                    </Typography>
                  </Stack>
                </CardContent>
              </Card>
            ) : null}
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, lg: embedded ? 12 : 3, xl: embedded ? 12 : 3 }}>
          <DetectionMap
            detections={rows}
            selected={selected}
            onSelect={setSelected}
          />
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
  );
}
