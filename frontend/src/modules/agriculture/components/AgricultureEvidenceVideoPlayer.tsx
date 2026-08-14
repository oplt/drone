import { Alert, Box, Button, Stack } from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { buildMissionVideoStreamUrl } from "../../video-analysis/api";

function timestampLabel(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(3).padStart(6, "0")}`;
}

export function AgricultureEvidenceVideoPlayer({
  videoId,
  timestampSeconds,
}: {
  videoId: string;
  timestampSeconds: number;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [windowEnd, setWindowEnd] = useState<number | null>(null);
  const seekToEvent = () => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = timestampSeconds;
    videoRef.current.pause();
    setWindowEnd(null);
  };

  useEffect(() => {
    seekToEvent();
    // The selected evidence timestamp is the synchronization source.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timestampSeconds, videoId]);

  const playWindow = () => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, timestampSeconds - 2);
    setWindowEnd(timestampSeconds + 2);
    void video.play().catch(() => setWindowEnd(null));
  };

  return (
    <Stack spacing={0.75}>
      <Box sx={{ bgcolor: "common.black", borderRadius: 1, overflow: "hidden" }}>
        <video
          ref={videoRef}
          controls
          preload="metadata"
          src={buildMissionVideoStreamUrl(videoId)}
          onLoadedMetadata={seekToEvent}
          onTimeUpdate={(event) => {
            if (windowEnd != null && event.currentTarget.currentTime >= windowEnd) {
              event.currentTarget.pause();
              setWindowEnd(null);
            }
          }}
          style={{ display: "block", width: "100%", maxHeight: 280 }}
          aria-label={`Source video at event ${timestampLabel(timestampSeconds)}`}
        />
      </Box>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button variant="outlined" onClick={seekToEvent} sx={{ minHeight: 44 }}>
          Seek to event
        </Button>
        <Button variant="outlined" onClick={playWindow} sx={{ minHeight: 44 }}>
          Play ±2 seconds
        </Button>
      </Stack>
      <Alert severity="info" icon={false}>
        Event {timestampLabel(timestampSeconds)} · source video {videoId}
      </Alert>
    </Stack>
  );
}
