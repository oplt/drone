# Performance baseline (Phase 0)

Reproducible baseline for backend, video, agriculture, training, and frontend
performance before optimization work. This document does not change production
behavior.

## Quick capture

Run the baseline recorder after checkout:

```sh
python3 backend/scripts/benchmarks/capture_performance_baseline.py
```

Output: `docs/benchmarks/performance-baseline-record.json`

Optional frontend bundle totals (requires a prior production build):

```sh
cd frontend
npm run build
cd ..
python3 backend/scripts/benchmarks/capture_performance_baseline.py
```

## What to measure

| Area | Metric | How |
|------|--------|-----|
| Agriculture API | p50 / p95 latency on read endpoints | `hey` or Vegeta against a running API |
| Agriculture UI | Request count with analysis page open | Browser devtools network or proxy logs for 60s |
| Video pipeline | Decode FPS, inference FPS, stage seconds | Video benchmark harness (below) |
| End-to-end analysis | Seconds per source-video minute | `total_seconds / video_minutes` from benchmark report |
| GPU | Utilization during inference/training | `nvidia-smi dmon -s u -d 5` |
| Training | Epoch duration, worker count | Vision training run detail metadata |
| Agriculture queue | Job wait time | Prometheus `agriculture_queue_age_seconds` |
| Time to first finding | Upload/flight completion → first actionable finding | Run audit timestamps + findings API |
| Frontend bundles | Route/chunk sizes | `npm run bundle:size` after `npm run build` |

## Video analysis harness

Fixture mode (no GPU; machine-readable stage timings):

```sh
python3 backend/scripts/benchmarks/run_video_analysis_benchmark.py \
  backend/scripts/benchmarks/video_analysis_manifest.small.example.json \
  --fixture

python3 backend/scripts/benchmarks/run_video_analysis_benchmark.py \
  backend/scripts/benchmarks/video_analysis_manifest.example.json \
  --fixture
```

Video decoder benchmark (TASK 3.1; does not modify production decode code):

```sh
python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \
  --fixture --output docs/benchmarks/video-decoder-report.json

python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \
  --render-markdown docs/benchmarks/video-decoder-report.json \
  --markdown-output docs/benchmarks/video-decoder-benchmark.md
```

See `docs/benchmarks/video-decoder-benchmark.md` for timing methodology and mode definitions.

Optional decoder switch (TASK 3.2; default unchanged):

```sh
# Opt-in after live TASK 3.1 benchmark on target hardware
export VIDEO_ANALYSIS_DECODER=ffmpeg_pipe   # or pyav_sequential, opencv_seek
# Legacy seek flag still maps sequential -> seek when decoder left at default
export VIDEO_ANALYSIS_DECODE_STRIDE_ENABLED=1
```

Bounded decode/inference prefetch (TASK 3.3; default on):

```sh
# Frames buffered between decode and GPU inference (default: max(2, min(batch*2, 8)))
export VIDEO_ANALYSIS_INFERENCE_PREFETCH_SIZE=4
```

Inference batch-size benchmark (TASK 3.4; default auto 8 CUDA / 1 CPU):

```sh
python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \
  --fixture --output docs/benchmarks/video-inference-batch-report.json

python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \
  --render-markdown docs/benchmarks/video-inference-batch-report.json \
  --markdown-output docs/benchmarks/video-inference-batch-benchmark.md
```

See `docs/benchmarks/video-inference-batch-benchmark.md` for per-profile recommendations.
Override only after live benchmark on target hardware:

```sh
export VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE=4
```

FP32/FP16 evaluation (TASK 3.7; production profiles remain FP32):

```sh
python3 backend/scripts/benchmarks/run_video_precision_benchmark.py \
  --fixture \
  --output docs/benchmarks/video-precision-report.json \
  --markdown-output docs/benchmarks/video-precision-benchmark.md
```

For a live run, set `validation_data` in
`backend/scripts/benchmarks/video_precision_manifest.example.json` to the audited
dataset configuration and omit `--fixture`. FP16 promotion requires live CUDA
evidence satisfying every registered accuracy and throughput gate.

TensorRT feasibility (TASK 3.8) is evidence-gated:

```sh
python3 backend/scripts/benchmarks/run_tensorrt_feasibility.py
```

The runner reads the recorded end-to-end and precision reports. It does not export
an engine unless both are live target-worker measurements and inference accounts
for at least half of end-to-end runtime. The current report is therefore deferred;
no production runtime or artifact is changed.

Stage keys now include `prefetch_queue_wait_ms` and `prefetch_queue_depth_max` in video analysis reports.

Live GPU/video runs use the same manifest format once wired; until then, record
fixture timings as placeholders and replace with measured values from a
representative workstation.

Stage keys expected in reports:

- `queue_wait`, `decode`, `inference`, `tracking`, `telemetry`, `crop`,
  `persist`, `summary`, `total`

Derived metrics:

- **Decode FPS**: `selected_frames / decode_seconds`
- **Inference FPS**: `frames_per_second` from harness output
- **Analysis seconds per video minute**: `total_seconds / (video_duration_seconds / 60)`

## Agriculture API latency

With local API on port 8000 and a valid analysis run id:

```sh
hey -n 200 -c 10 -m GET \
  -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/agriculture/analysis-runs/$RUN_ID/findings?limit=25"
```

Record p50/p95 from `hey` summary. Repeat for fusion, crop-risk, and run detail
endpoints while the analysis page is open to compare request churn (see TASK 1.1).

## Prometheus / observability

Local stack: see `docs/local-observability.md`.

Useful series:

- `media_pipeline_stage_duration_seconds{pipeline,stage}` — canonical bounded stage timings (video + agriculture)
- `agriculture_run_duration_seconds`
- `agriculture_inference_latency_seconds`
- `agriculture_queue_age_seconds`
- `agriculture_queue_depth`
- `agriculture_worker_saturation`
- `drone_video_analysis_jobs_total`

App metrics endpoint: `http://127.0.0.1:8000/metrics`

## Frontend bundle sizes

Map shell budget (no eager Google Maps / Cesium preloads):

```sh
cd frontend
npm run build
npm run check:bundle-budgets
npm run bundle:size
```

Record total MiB and top chunks for agriculture, vision training, maps, and
video analysis routes by loading each route once in a production preview and
inspecting network chunks, or from `dist/assets/*` after build.

## Recorded baseline

Latest machine-readable snapshot:

- `docs/benchmarks/performance-baseline-record.json`

Update after hardware or dependency changes that affect performance claims.

## Related tasks

- **TASK 0.2**: Named timing metrics on the media pipeline (`backend/observability/media_pipeline_metrics.py`)
- **TASK 0.3**: Performance-regression checklist in contributor docs (`docs/performance-regression-checklist.md`)
- **TASK 1.1**: Stop agriculture polling after terminal analysis states
