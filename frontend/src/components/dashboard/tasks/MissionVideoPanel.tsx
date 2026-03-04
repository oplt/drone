import { Box, Button, CircularProgress, Paper, Stack, Typography } from "@mui/material";
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
  telemetry: any;
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
  onVideoError,
  onVideoLoad,
  onRetry,
}: MissionVideoPanelProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: 2,
        borderColor: "hsla(174, 30%, 40%, 0.25)",
        background: "hsla(0, 0%, 100%, 0.7)",
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
          {startingVideo && <CircularProgress size={16} />}
          <Typography variant="caption" color="text.secondary">
            {startingVideo
              ? "Starting video…"
              : videoError
              ? "Error"
              : droneConnected
              ? "Live"
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
        {droneConnected ? (
          <>
            {videoError ? (
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
                  Retry attempt {videoRetryCount}...
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  sx={{ mt: 2, color: "white", borderColor: "grey.600" }}
                  onClick={onRetry}
                >
                  Retry Now
                </Button>
              </Box>
            ) : (
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

                <TelemetryHud telemetry={telemetry} sx={{ top: 8, left: 8 }} />
              </>
            )}

            {startingVideo && (
              <Box
                sx={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  backgroundColor: "rgba(0,0,0,0.7)",
                }}
              >
                <CircularProgress />
              </Box>
            )}
          </>
        ) : (
          <Typography sx={{ color: "white" }}>{disconnectedMessage}</Typography>
        )}
      </Box>
    </Paper>
  );
}
