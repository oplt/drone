import { Box, Card, CardContent, Typography } from "@mui/material";
import type { VideoDetection } from "../types";

type Props = {
  detections: VideoDetection[];
  selected: VideoDetection | null;
  durationSeconds: number;
  status?: string;
  onSelect: (detection: VideoDetection) => void;
};

export function DetectionTimeline({ detections, selected, durationSeconds, status, onSelect }: Props) {
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
            {detections.map((detection) => (
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
                  top: selected?.id === detection.id ? 5 : 13,
                  width: selected?.id === detection.id ? 8 : 5,
                  height: selected?.id === detection.id ? 38 : 22,
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
