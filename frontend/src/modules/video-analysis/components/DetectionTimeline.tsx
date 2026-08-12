import { Box, Card, CardContent, Typography } from "@mui/material";
import { useMemo } from "react";
import type { DetectionAggregateBucket, VideoDetection } from "../types";

type Props = {
  buckets?: DetectionAggregateBucket[];
  detections: VideoDetection[];
  selected: VideoDetection | null;
  durationSeconds: number;
  status?: string;
  onSelect: (detection: VideoDetection) => void;
  onSelectBucket?: (bucket: DetectionAggregateBucket) => void;
};

export function DetectionTimeline({
  buckets,
  detections,
  selected,
  durationSeconds,
  status,
  onSelect,
  onSelectBucket,
}: Props) {
  const aggregateControls = useMemo(() => {
    if (!buckets?.length) return null;
    return buckets.map((bucket) => {
      const total = Object.values(bucket.class_counts).reduce(
        (sum, count) => sum + count,
        0,
      );
      const mid = (bucket.start_seconds + bucket.end_seconds) / 2;
      return { bucket, total, mid };
    });
  }, [buckets]);

  const detailControls = useMemo(() => {
    if (aggregateControls) return [];
    if (detections.length <= 100) return detections;
    const bucketSeconds = Math.max(1, durationSeconds / 100);
    const byBucket = new Map<number, VideoDetection>();
    detections.forEach((detection) => {
      const index = Math.floor(detection.timestamp_seconds / bucketSeconds);
      const current = byBucket.get(index);
      if (!current || detection.confidence > current.confidence) {
        byBucket.set(index, detection);
      }
    });
    return [...byBucket.values()];
  }, [aggregateControls, detections, durationSeconds]);

  const empty =
    (aggregateControls ? aggregateControls.length === 0 : detections.length === 0);

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Detection timeline
        </Typography>
        {empty ? (
          <Typography variant="body2" color="text.secondary">
            {status === "completed"
              ? "Analysis finished with no matching detections."
              : "Detections appear here while processing."}
          </Typography>
        ) : (
          <Box
            sx={{
              position: "relative",
              height: 48,
              bgcolor: "action.hover",
              borderRadius: 1,
            }}
          >
            {aggregateControls
              ? aggregateControls.map(({ bucket, total, mid }) => (
                  <Box
                    component="button"
                    type="button"
                    aria-label={`Review ${total} detections from ${bucket.start_seconds.toFixed(1)} to ${bucket.end_seconds.toFixed(1)} seconds`}
                    key={`${bucket.start_seconds}-${bucket.end_seconds}`}
                    onClick={() => onSelectBucket?.(bucket)}
                    sx={{
                      position: "absolute",
                      p: 0,
                      border: 0,
                      left: `${Math.min(
                        99,
                        Math.max(0, (mid / Math.max(durationSeconds, 1)) * 100),
                      )}%`,
                      top: 2,
                      width: 44,
                      height: 44,
                      transform: "translateX(-50%)",
                      opacity: 0.55 + Math.min(0.45, total / 40),
                      bgcolor: "primary.main",
                      borderRadius: 1,
                      cursor: "pointer",
                      "&:focus-visible": {
                        outline: "2px solid",
                        outlineColor: "primary.dark",
                      },
                    }}
                  />
                ))
              : detailControls.map((detection) => (
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
                      left: `${Math.min(
                        99,
                        Math.max(
                          0,
                          (detection.timestamp_seconds /
                            Math.max(durationSeconds, 1)) *
                            100,
                        ),
                      )}%`,
                      top: 2,
                      width: 44,
                      height: 44,
                      transform: "translateX(-50%)",
                      opacity: selected?.id === detection.id ? 1 : 0.55,
                      bgcolor:
                        selected?.id === detection.id
                          ? "warning.main"
                          : "primary.main",
                      borderRadius: 1,
                      cursor: "pointer",
                      "&:focus-visible": {
                        outline: "2px solid",
                        outlineColor: "primary.dark",
                      },
                    }}
                  />
                ))}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
