import { Box, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { useDetectionFps } from "../hooks/useDetectionFps";
import { useLiveObjectDetection } from "../hooks/useLiveObjectDetection";
import { LiveDetectionOverlay } from "./LiveDetectionOverlay";
import { TelemetryHud } from "./TelemetryHud";

type MissionVideoPanelProps = {
  title: string;
  imgAlt: string;
  disconnectedMessage: string;
  apiBase: string;
  streamKey: number;
  videoToken: string | null;
  startingVideo: boolean;
  videoError: string | null;
  videoRetryCount: number;
  droneConnected: boolean;
  telemetry: unknown;
  missionLabel?: string | null;
  recordingStatus?: string | null;
  onVideoError: () => void;
  onVideoLoad: () => void;
  onRetry: () => void;
};

export function MissionVideoPanel({
  title,
  imgAlt,
  disconnectedMessage,
  apiBase,
  streamKey,
  videoToken,
  startingVideo,
  videoError,
  videoRetryCount,
  droneConnected,
  telemetry,
  missionLabel,
  recordingStatus,
  onVideoError,
  onVideoLoad,
  onRetry,
}: MissionVideoPanelProps) {
  const shouldRenderStream = droneConnected && streamKey > 0 && !videoError;
  const objectDetection = useLiveObjectDetection();
  const detectionFps = useDetectionFps(
    objectDetection.status?.frames_processed,
    objectDetection.enabled,
  );

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: 2,
        borderColor: "divider",
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1 }}
      >
        <Typography variant="subtitle1">{title}</Typography>
        <Stack direction="row" alignItems="center" spacing={1}>
          <ActionIconButton
            variant={objectDetection.enabled ? "visibility" : "visibility-off"}
            title={objectDetection.enabled ? "Detection On" : "Enable Detection"}
            color={objectDetection.enabled ? "success" : "primary"}
            disabled={!droneConnected || objectDetection.toggling}
            onClick={objectDetection.toggle}
          />
          {startingVideo && <CircularProgress size={16} />}
          <Typography variant="caption" color="text.secondary">
            {startingVideo
              ? "Starting video…"
              : videoError
              ? "Error"
              : shouldRenderStream
              ? "Live"
              : droneConnected
              ? "Ready"
              : "Disconnected"}
          </Typography>
        </Stack>
      </Stack>

      <Box
        sx={{
          width: "100%",
          height: 240,
          bgcolor: "#000",
          borderRadius: 1,
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
        }}
      >
        {!droneConnected ? (
          <Typography sx={{ color: "white" }}>{disconnectedMessage}</Typography>
        ) : videoError ? (
          <Box
            sx={{
              width: "100%",
              height: "100%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              bgcolor: "rgba(0,0,0,0.85)",
              color: "warning.main",
              p: 2,
              textAlign: "center",
            }}
          >
            <Typography variant="h6" sx={{ color: "warning.main", mb: 1 }}>
              ⚠️ Video Stream Unavailable
            </Typography>
            <Typography variant="body2" sx={{ color: "grey.400", mb: 2 }}>
              {videoError}
            </Typography>
            <Typography variant="caption" sx={{ color: "grey.500" }}>
              Retry attempt {videoRetryCount}
            </Typography>
            <ActionIconButton
              variant="retry"
              title="Retry Now"
              onClick={onRetry}
              sx={{ mt: 2, color: "white", borderColor: "grey.600" }}
            />
          </Box>
        ) : shouldRenderStream ? (
          <>
            <Box
              component="img"
              src={`${apiBase}/video/mjpeg?key=${streamKey}${
                videoToken ? `&token=${encodeURIComponent(videoToken)}` : ""
              }`}
              alt={imgAlt}
              onError={onVideoError}
              onLoad={onVideoLoad}
              sx={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
            <TelemetryHud
              telemetry={telemetry}
              cameraTitle={title}
              missionLabel={missionLabel}
              recordingStatus={recordingStatus ?? (shouldRenderStream ? "Live" : null)}
              detection={{
                enabled: objectDetection.enabled,
                modelName: objectDetection.status?.config?.detector_model_path ?? null,
                fps: detectionFps,
                framesProcessed: objectDetection.status?.frames_processed,
                lastError: objectDetection.error,
              }}
            />
            {objectDetection.enabled ? (
              <LiveDetectionOverlay detections={objectDetection.detections} />
            ) : null}
          </>
        ) : (
          <Typography sx={{ color: "white" }}>
            Waiting for mission video stream…
          </Typography>
        )}

        {startingVideo && (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: "rgba(0,0,0,0.7)",
            }}
          >
            <CircularProgress />
          </Box>
        )}
      </Box>
      {objectDetection.error ? (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: "block" }}>
          Object detection: {objectDetection.error}
        </Typography>
      ) : null}
    </Paper>
  );
}
