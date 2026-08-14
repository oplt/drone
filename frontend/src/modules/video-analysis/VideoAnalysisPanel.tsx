import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Divider,
  Grid,
  Stack,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { AnalysisWorkflowTabs, CollapsibleDetectionLogs } from "./components/AnalysisWorkflowTabs";
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
  useDetectionAggregates,
  useDetectionWindow,
  useDetections,
  useLiveSavedDetections,
  useMissionVideos,
  useStartAnalysis,
  useUploadVideo,
} from "./hooks";
import { DEFAULT_MODEL } from "./modelOptions";
import type {
  AnalyzeVideoPayload,
  DetectionAggregateBucket,
  VideoAsset,
  VideoDetection,
} from "./types";

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
  const [selectedBucket, setSelectedBucket] =
    useState<DetectionAggregateBucket | null>(null);
  const theme = useTheme();
  const mobileLayout = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileTab, setMobileTab] = useState<"player" | "results" | "map">("player");

  const queryMissionId = missionId;
  const missionVideos = useMissionVideos(queryMissionId, fieldId, {
    flightActive,
  });
  const refetchMissionVideos = missionVideos.refetch;
  const upload = useUploadVideo();
  const start = useStartAnalysis();
  const job = useAnalysisJob(jobId);
  const detections = useDetections(jobId, job.data?.status);
  const aggregates = useDetectionAggregates(
    jobId,
    job.data?.status,
    durationSeconds,
  );
  const windowDetections = useDetectionWindow(
    jobId,
    selectedBucket
      ? {
          sinceTs: selectedBucket.start_seconds,
          untilTs: selectedBucket.end_seconds,
        }
      : null,
  );
  const summary = useAnalysisSummary(jobId, job.data?.status);
  const cancel = useCancelAnalysis();
  const liveDetections = useLiveSavedDetections();
  const activeVideo =
    video ?? (!file ? (missionVideos.data?.[0] ?? null) : null);
  const playbackUrl = useMemo(
    () =>
      activeVideo && !file ? buildMissionVideoStreamUrl(activeVideo.id) : null,
    [file, activeVideo],
  );

  const rows = useMemo(() => {
    const windowItems = windowDetections.data?.items;
    if (windowItems?.length) return windowItems;
    return detections.data?.items ?? [];
  }, [detections.data?.items, windowDetections.data?.items]);
  const evidenceMatch = useMemo(() => {
    if (!requestedEvidenceId) return null;
    return rows.find((row) => row.id === requestedEvidenceId) ?? null;
  }, [requestedEvidenceId, rows]);
  const bucketBest = useMemo(() => {
    if (!selectedBucket) return null;
    const items = windowDetections.data?.items;
    if (!items?.length) return null;
    return [...items].sort((left, right) => right.confidence - left.confidence)[0] ?? null;
  }, [selectedBucket, windowDetections.data?.items]);
  const displaySelected = selected ?? evidenceMatch ?? bucketBest;
  const topLabels = useMemo(() => {
    const counts = summary.data?.detections_by_class;
    if (!counts) return [];
    return Object.entries(counts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5);
  }, [summary.data?.detections_by_class]);
  const detectionCount =
    summary.data
      ? Object.values(summary.data.detections_by_class).reduce(
          (sum, count) => sum + count,
          0,
        )
      : (detections.data?.total_estimate ?? rows.length);
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

  const chooseFile = (next: File | null, validationError: string | null) => {
    setFile(next);
    setFileError(validationError);
    setVideo(null);
    setJobId(null);
    setSelected(null);
    setSelectedBucket(null);
  };

  const selectMissionRecording = (recording: VideoAsset) => {
    setFile(null);
    setFileError(null);
    setVideo(recording);
    setJobId(null);
    setSelected(null);
    setSelectedBucket(null);
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
    if (!activeVideo) return;
    const created = await start.mutateAsync({ videoId: activeVideo.id, payload });
    setVideo(activeVideo);
    setJobId(created.id);
    setSelected(null);
    setSelectedBucket(null);
  };

  const workflowPanel = (
    <AnalysisWorkflowTabs
      file={file}
      video={activeVideo}
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
      onVideoUpdated={setVideo}
      metadataReady={Boolean(activeVideo?.captured_at)}
      job={job.data}
      detectionCount={detectionCount}
      detections={rows}
      cancelling={cancel.isPending}
      onCancel={jobId ? () => cancel.mutate(jobId) : undefined}
    />
  );

  const playerPanel = (
    <Stack spacing={2}>
      <VideoOverlayPlayer
        file={file}
        playbackUrl={playbackUrl}
        detections={rows}
        selected={displaySelected}
        onDurationChange={setDurationSeconds}
      />
      <DetectionTimeline
        buckets={aggregates.data?.buckets}
        detections={rows}
        selected={displaySelected}
        durationSeconds={durationSeconds}
        status={job.data?.status}
        onSelect={setSelected}
        onSelectBucket={setSelectedBucket}
      />
    </Stack>
  );

  const resultsPanel = (
    <Stack spacing={2}>
      {topLabels.length ? (
        <Alert severity="info">
          Frequent detections:{" "}
          {topLabels.map(([label, count]) => `${label}: ${count}`).join(" | ")}
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
                  <Typography variant="subtitle2">Unique tracked objects</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Estimated from tracker continuity; camera motion and sampling
                    affect counts.
                  </Typography>
                  {Object.entries(summary.data.unique_tracked_objects_by_class).map(
                    ([label, count]) => (
                      <Stack key={label} direction="row" justifyContent="space-between">
                        <Typography>{label.replaceAll("_", " ")}</Typography>
                        <Typography fontWeight={600}>{count.toLocaleString()}</Typography>
                      </Stack>
                    ),
                  )}
                </Box>
              ) : null}
              <Divider />
              <Box>
                <Typography variant="subtitle2">Frame detections</Typography>
                {Object.entries(summary.data.detections_by_class).map(([label, count]) => (
                  <Stack key={label} direction="row" justifyContent="space-between">
                    <Typography>{label.replaceAll("_", " ")}</Typography>
                    <Typography fontWeight={600}>{count.toLocaleString()}</Typography>
                  </Stack>
                ))}
              </Box>
              <Typography variant="body2" color="text.secondary">
                Model: {summary.data.model_name} · Tracking{" "}
                {summary.data.tracking_enabled ? "enabled" : "off"} · Small-object mode{" "}
                {summary.data.small_object_mode ? "enabled" : "off"}
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      ) : (
        <Alert severity="info">Run analysis to see class summaries and tracking results.</Alert>
      )}
    </Stack>
  );

  const mapLogsPanel = (
    <Stack spacing={2}>
      <DetectionMap
        detections={rows}
        selected={displaySelected}
        onSelect={setSelected}
      />
      <CollapsibleDetectionLogs
        defaultExpanded={
          job.data?.status === "completed" || job.data?.status === "failed"
        }
      >
        <DetectionLogsTabs
          liveRows={liveDetections.data ?? []}
          liveLoading={liveDetections.isLoading}
          jobRows={rows}
          jobLoading={detections.isLoading}
          onJobRowSelect={setSelected}
        />
      </CollapsibleDetectionLogs>
    </Stack>
  );

  return (
    <Stack
      spacing={2}
      sx={{ pt: embedded ? 0.5 : 0, overflowX: "hidden", width: "100%" }}
    >
      {!embedded ? (
        <Box>
          <Typography variant="overline" color="primary">
            Offline intelligence
          </Typography>
          <Typography variant="h4" fontWeight={600}>
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

      {mobileLayout ? (
        <Stack spacing={1.5}>
          {workflowPanel}
          <Tabs
            value={mobileTab}
            onChange={(_, value: "player" | "results" | "map") => setMobileTab(value)}
            variant="fullWidth"
            aria-label="Video analysis mobile sections"
          >
            <Tab value="player" label="Player" id="video-mobile-tab-player" aria-controls="video-mobile-panel-player" />
            <Tab value="results" label="Results" id="video-mobile-tab-results" aria-controls="video-mobile-panel-results" />
            <Tab value="map" label="Map / Logs" id="video-mobile-tab-map" aria-controls="video-mobile-panel-map" />
          </Tabs>
          <Box
            role="tabpanel"
            id={`video-mobile-panel-${mobileTab}`}
            aria-labelledby={`video-mobile-tab-${mobileTab}`}
          >
            {mobileTab === "player"
              ? playerPanel
              : mobileTab === "results"
                ? resultsPanel
                : mapLogsPanel}
          </Box>
        </Stack>
      ) : (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: embedded ? 12 : 3, xl: embedded ? 4 : 3 }}>
            {workflowPanel}
          </Grid>
          <Grid size={{ xs: 12, lg: embedded ? 12 : 6, xl: embedded ? 8 : 6 }}>
            <Stack spacing={2}>
              {playerPanel}
              {resultsPanel}
            </Stack>
          </Grid>
          <Grid size={{ xs: 12, lg: embedded ? 12 : 3, xl: embedded ? 12 : 3 }}>
            <DetectionMap
              detections={rows}
              selected={displaySelected}
              onSelect={setSelected}
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <CollapsibleDetectionLogs
              defaultExpanded={
                job.data?.status === "completed" || job.data?.status === "failed"
              }
            >
              <DetectionLogsTabs
                liveRows={liveDetections.data ?? []}
                liveLoading={liveDetections.isLoading}
                jobRows={rows}
                jobLoading={detections.isLoading}
                onJobRowSelect={setSelected}
              />
            </CollapsibleDetectionLogs>
          </Grid>
        </Grid>
      )}
    </Stack>
  );
}
