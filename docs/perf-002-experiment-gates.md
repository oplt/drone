# PERF-002 experiment gates

PERF-002 keeps the validated pipeline as the default and gates optimization
experiments through runtime environment variables.

## Prerequisite

Capture the PERF-001 baseline on the same video corpus, hardware, model
artifact hash, confidence threshold, and frame stride before enabling a gate.
Record throughput, stage latency, selected frame indices/timestamps, detection
count, classes, confidence, and bounding boxes.

## Gates

- `VIDEO_ANALYSIS_DECODE_STRIDE_ENABLED=true` seeks directly to the canonical
  sampled frame indices instead of decoding intervening frames.
- `VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE=N` enables bounded standard-detector
  batches when `N > 1`. SAHI and tracking remain unbatched.
- `VIDEO_ANALYSIS_DEFER_LOW_CONFIDENCE_CROPS=true` retains the existing policy
  of writing crops only above the configured confidence threshold or for
  tracked detections.

Enable one experiment at a time. The default values (`false`, `1`, and `true`)
are the validated baseline.

## Parity and rollback

Selected frame indices and derived timestamps must match exactly. Detection
class/count must match; confidence and box coordinates may differ only by
`1e-5` to account for runtime numeric variation. Evidence checksums must match
when detections match.

Rollback is immediate: set decode stride to `false` and batch size to `1`
(and restore deferred crops to `true`) and restart video-analysis workers.
