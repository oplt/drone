import { Box } from "@mui/material";
import type { LiveFrameDetection } from "../api/liveObjectDetectionApi";

type Props = {
  detections: LiveFrameDetection[];
};

export function LiveDetectionOverlay({ detections }: Props) {
  if (!detections.length) return null;
  const { image_width: width, image_height: height } = detections[0];

  return (
    <Box
      component="svg"
      aria-label="Live object detections"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid slice"
      sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
    >
      {detections.map((detection, index) => {
        const [x1, y1, x2, y2] = detection.bbox;
        return (
          <g key={`${detection.label}-${index}`}>
            <rect
              x={x1}
              y={y1}
              width={Math.max(0, x2 - x1)}
              height={Math.max(0, y2 - y1)}
              fill="none"
              stroke="#00e676"
              strokeWidth={2}
            />
            <text
              x={x1}
              y={Math.max(14, y1 - 5)}
              fill="#00e676"
              fontSize={14}
              fontWeight={700}
            >
              {detection.label} {Math.round(detection.confidence * 100)}%
            </text>
          </g>
        );
      })}
    </Box>
  );
}
