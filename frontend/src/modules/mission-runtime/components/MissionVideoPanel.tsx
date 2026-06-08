import {
  Box,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import type { SxProps, Theme } from "@mui/material/styles";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { useDetectionFps } from "../hooks/useDetectionFps";
import { useLiveObjectDetection } from "../hooks/useLiveObjectDetection";
import { LiveDetectionOverlay } from "./LiveDetectionOverlay";
import { MissionVideoEmptyState } from "./MissionVideoEmptyState";
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
  frameHeight?: number;
  frameSx?: SxProps<Theme>;
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
  frameHeight = 240,
  frameSx,
}: MissionVideoPanelProps) {
  const shouldRenderStream = droneConnected && streamKey > 0 && !videoError;
  const streamStatus = startingVideo
    ? "Starting"
    : videoError
      ? "Error"
      : shouldRenderStream
        ? "Ready"
        : "Waiting";
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
        borderRadius: 3,
        borderColor: "divider",
        width: "100%",
        alignSelf: "stretch",
        flexShrink: 0,
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
          <Chip
            size="small"
            label={streamStatus}
            color={
              videoError ? "error" : shouldRenderStream ? "success" : "warning"
            }
            variant={shouldRenderStream || videoError ? "filled" : "outlined"}
          />
          <ActionIconButton
            variant={objectDetection.enabled ? "visibility" : "visibility-off"}
            title={
              objectDetection.enabled ? "Detection On" : "Enable Detection"
            }
            color={objectDetection.enabled ? "success" : "primary"}
            disabled={!droneConnected || objectDetection.toggling}
            onClick={objectDetection.toggle}
          />
          {startingVideo && <CircularProgress size={16} />}
        </Stack>
      </Stack>

      <Box
        className="mission-video-frame"
        sx={[
          {
            width: "100%",
            minHeight: frameHeight,
            height: frameHeight,
            flexShrink: 0,
            bgcolor: "#000",
            borderRadius: 2,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            position: "relative",
            boxSizing: "border-box",
          },
          ...(frameSx ? (Array.isArray(frameSx) ? frameSx : [frameSx]) : []),
        ]}
      >
        {!droneConnected ? (
          <MissionVideoEmptyState
            title={disconnectedMessage}
            description="Start flight or connect camera stream to preview live feed."
          />
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
            <Typography
              variant="subtitle1"
              sx={{ color: "warning.main", mb: 1, fontWeight: 700 }}
            >
              Video stream unavailable
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
              recordingStatus={
                recordingStatus ?? (shouldRenderStream ? "Live" : null)
              }
              detection={{
                enabled: objectDetection.enabled,
                modelName:
                  objectDetection.status?.config?.detector_model_path ?? null,
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
          <MissionVideoEmptyState
            title="Waiting for mission video stream"
            description="Start flight or connect camera stream to preview live feed."
          />
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
        <Typography
          variant="caption"
          color="error"
          sx={{ mt: 1, display: "block" }}
        >
          Object detection: {objectDetection.error}
        </Typography>
      ) : null}
    </Paper>
  );
}
