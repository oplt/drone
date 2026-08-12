import { Box, Card, CardContent, Typography } from "@mui/material";
import { useMemo } from "react";
import type { VideoDetection } from "../types";

type Props = {
  detections: VideoDetection[];
  selected: VideoDetection | null;
  durationSeconds: number;
  status?: string;
  onSelect: (detection: VideoDetection) => void;
};

export function DetectionTimeline({ detections, selected, durationSeconds, status, onSelect }: Props) {
  const controls = useMemo(() => {
    if (detections.length <= 100) return detections;
    const bucketSeconds = Math.max(1, durationSeconds / 100);
    const buckets = new Map<number, VideoDetection>();
    detections.forEach((detection) => {
      const bucket = Math.floor(detection.timestamp_seconds / bucketSeconds);
      const current = buckets.get(bucket);
      if (!current || detection.confidence > current.confidence) {
        buckets.set(bucket, detection);
      }
    });
    return [...buckets.values()];
  }, [detections, durationSeconds]);
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>Detection timeline</Typography>
        {detections.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {status === "completed" ? "Analysis finished with no matching detections." : "Detections appear here while processing."}
          </Typography>
        ) : (
          <Box sx={{ position: "relative", height: 48, bgcolor: "action.hover", borderRadius: 1 }}>
            {controls.map((detection) => (
              <Box
                component="button"
                type="button"
                aria-label={`Review ${detection.label} at ${detection.timestamp_seconds.toFixed(1)} seconds`}
                key={detection.id}
                onClick={() => onSelect(detection)}
                sx={{
                  position: "absolute",
                  p: 0,
                  border: 0,
                  left: `${Math.min(99, Math.max(0, (detection.timestamp_seconds / durationSeconds) * 100))}%`,
                  top: 2,
                  width: 44,
                  height: 44,
                  transform: "translateX(-50%)",
                  opacity: selected?.id === detection.id ? 1 : 0.55,
                  bgcolor: selected?.id === detection.id ? "warning.main" : "primary.main",
                  borderRadius: 1,
                  cursor: "pointer",
                  "&:focus-visible": { outline: "2px solid", outlineColor: "primary.dark" },
                }}
              />
            ))}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
