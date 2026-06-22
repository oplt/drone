import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Card, CardContent, Typography } from "@mui/material";
import type { VideoDetection } from "../types";

type Props = {
  file?: File | null;
  playbackUrl?: string | null;
  detections: VideoDetection[];
  selected?: VideoDetection | null;
  onDurationChange: (duration: number) => void;
};

export function VideoOverlayPlayer({ file, playbackUrl, detections, selected, onDurationChange }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoSize, setVideoSize] = useState({ width: 1, height: 1 });
  const [timeSeconds, setTimeSeconds] = useState(0);
  const objectUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  const videoSrc = objectUrl ?? playbackUrl ?? null;

  useEffect(() => () => { if (objectUrl) URL.revokeObjectURL(objectUrl); }, [objectUrl]);

  useEffect(() => {
    if (!selected || !videoRef.current) return;
    videoRef.current.currentTime = selected.timestamp_seconds;
    videoRef.current.pause();
  }, [selected]);

  const displayedTime = selected?.timestamp_seconds ?? timeSeconds;
  const active = detections.filter((detection) => Math.abs(detection.timestamp_seconds - displayedTime) < 0.15);

  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>Video review</Typography>
        <Box sx={{ position: 'relative', width: '100%', aspectRatio: '16/9', bgcolor: 'black', borderRadius: 1, overflow: 'hidden' }}>
          {videoSrc ? (
            <video
              ref={videoRef}
              src={videoSrc}
              controls
              onTimeUpdate={(event) => setTimeSeconds(event.currentTarget.currentTime)}
              onLoadedMetadata={() => {
                const v = videoRef.current;
                if (v) {
                  setVideoSize({ width: v.videoWidth || 1, height: v.videoHeight || 1 });
                  onDurationChange(Math.max(1, v.duration || 1));
                }
              }}
              style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
            />
          ) : (
            <Box sx={{ height: '100%', display: 'grid', placeItems: 'center', color: 'text.secondary' }}>Select a mission recording or upload a video to preview it here.</Box>
          )}

          {active.map((d) => (
            <Box key={d.id} sx={{
              position: 'absolute',
              left: `${(d.x1 / videoSize.width) * 100}%`,
              top: `${(d.y1 / videoSize.height) * 100}%`,
              width: `${((d.x2 - d.x1) / videoSize.width) * 100}%`,
              height: `${((d.y2 - d.y1) / videoSize.height) * 100}%`,
              border: '2px solid', borderColor: 'warning.main', pointerEvents: 'none'
            }}>
              <Box sx={{ position: 'absolute', top: -24, left: 0, px: 0.75, bgcolor: 'warning.main', color: 'warning.contrastText', fontSize: 12, fontWeight: 700 }}>
                {d.label} {(d.confidence * 100).toFixed(0)}%
              </Box>
            </Box>
          ))}
        </Box>
      </CardContent>
    </Card>
  );
}
