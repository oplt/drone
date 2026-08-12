# PERF-002 experiment gates

PERF-002 keeps the validated pipeline as the default and gates optimization
experiments through runtime environment variables.

**Defaults stay OFF until a measured GO.** Do not enable decode-stride,
batch inference (`N > 1`), or other experiment flags in production (or as
shipped defaults) without a reproducible PERF-001 baseline and a parity-passing
experiment report.

## How to run the harness

From the repository root:

```bash
python backend/scripts/benchmarks/run_video_analysis_benchmark.py \
  backend/scripts/benchmarks/video_analysis_manifest.example.json \
  --fixture \
  --baseline-label baseline \
  --experiment-label decode-stride \
  --output /tmp/video-analysis-benchmark.json
```

`--fixture` uses synthetic stage timings and detection counts from the manifest
so CI and local machines without a GPU can still produce machine-readable JSON
and exercise parity stubs (frames / classes / counts). Live GPU runs remain
opt-in and must use the same manifest fields: `model_hash`, `hardware`,
`frame_stride_seconds`, `confidence_threshold`, SAHI/tracking flags, and
`parity_tolerances`.

Inspect `comparison.improvement_percent` and `parity.passed` before changing
any runtime gate. Record the artifact path and decision in this document when
promoting a GO.

## Prerequisite

Capture the PERF-001 baseline on the same video corpus, hardware, model
artifact hash, confidence threshold, and frame stride before enabling a gate.
Record throughput, stage latency, selected frame indices/timestamps, detection
count, classes, confidence, and bounding boxes.

## Gates

- `VIDEO_ANALYSIS_DECODE_STRIDE_ENABLED=true` seeks directly to the canonical
  sampled frame indices instead of decoding intervening frames.
  **Default: `false`.**
- `VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE=N` enables bounded standard-detector
  batches when `N > 1`. SAHI and tracking remain unbatched.
  **Default: `1`.**
- `VIDEO_ANALYSIS_DEFER_LOW_CONFIDENCE_CROPS=true` retains the existing policy
  of writing crops only above the configured confidence threshold or for
  tracked detections. **Default: `true` (validated baseline crop policy).**

Enable one experiment at a time. The default values (`false`, `1`, and `true`)
are the validated baseline and must remain the shipped defaults until a GO.

## Parity and rollback

Selected frame indices and derived timestamps must match exactly. Detection
class/count must match; confidence and box coordinates may differ only by
`1e-5` to account for runtime numeric variation. Evidence checksums must match
when detections match.

Rollback is immediate: set decode stride to `false` and batch size to `1`
(and restore deferred crops to `true`) and restart video-analysis workers.

## Measured GO log

| Date | Experiment | Manifest / report | Parity | Decision | Notes |
|------|------------|-------------------|--------|----------|-------|
| — | — | — | — | NO-GO (defaults off) | No production GO until measured |
