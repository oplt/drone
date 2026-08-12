import type { VideoDetection } from "./types";

export function buildDetectionTemporalIndex(
  detections: VideoDetection[],
): VideoDetection[] {
  return [...detections].sort(
    (left, right) =>
      left.timestamp_seconds - right.timestamp_seconds ||
      left.id.localeCompare(right.id),
  );
}

export function detectionsNearTime(
  index: VideoDetection[],
  timestampSeconds: number,
  toleranceSeconds = 0.15,
): VideoDetection[] {
  let low = 0;
  let high = index.length;
  const start = timestampSeconds - toleranceSeconds;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (index[middle].timestamp_seconds < start) low = middle + 1;
    else high = middle;
  }
  const matches: VideoDetection[] = [];
  for (
    let cursor = low;
    cursor < index.length &&
    index[cursor].timestamp_seconds <= timestampSeconds + toleranceSeconds;
    cursor += 1
  ) {
    matches.push(index[cursor]);
  }
  return matches;
}
