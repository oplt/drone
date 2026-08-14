# Agriculture stage scaling

Phase 6 runs the post-flight workflow as durable, idempotent Celery stages. The
API and `agriculture.process_run` coordinate work only; CPU, GPU, geospatial,
temporal, fusion, and export operations execute on their dedicated queues.

| Stage | Queue | Workload | Starting concurrency | Memory target | Soft / hard timeout | Scaling guidance |
|---|---|---|---:|---:|---:|---|
| RGB inference coordination | `agriculture-rgb-inference` | Low CPU coordination; heavy inference remains on `video-analysis` GPU workers | 1 coordinator; GPU workers 1 per GPU | 512 MiB coordinator; model-dependent GPU worker | 1500 / 1800 s | Scale `video-analysis` by available GPUs. Never place multiple model workers on one GPU until measured VRAM headroom proves it safe. |
| Geospatial aggregation | `agriculture-geospatial` | CPU, PostGIS, moderate memory | 2 | 2–4 GiB | 1080 / 1200 s | Scale horizontally when queue age rises and database CPU/IO remains below saturation. |
| RGB segmentation products | `agriculture-segmentation` | CPU today; GPU-capable when a released segmentation model exists | 1 per GPU for GPU releases; otherwise 2 CPU | 2–8 GiB, model-dependent | 1500 / 1800 s | Keep GPU releases isolated from coordination and geospatial queues. Benchmark batch size before raising concurrency. |
| Temporal comparison | `agriculture-temporal` | CPU/PostGIS reads and deterministic writes | 2 | 1–2 GiB | 840 / 900 s | Scale after geospatial capacity. Monitor spatial-query latency and connection-pool pressure. |
| Sensor fusion | `agriculture-fusion` | CPU/numeric and database IO | 2 | 1–2 GiB | 840 / 900 s | Scale for queues with calibrated multispectral/thermal inputs. Missing inputs skip cleanly and do not consume retry capacity. |
| Exports | `agriculture-exports` | CPU plus object-storage IO | 2 | 1–2 GiB | 840 / 900 s | Scale on queue age and storage latency. Keep this queue away from API and orchestration workers. |
| Dead letter | `agriculture-dead-letter` | Low CPU recovery metadata | 1 | 256 MiB | 90 / 120 s | One worker is normally sufficient; alert on any sustained depth above zero. |

The configured worker starting points are
`agriculture_worker_gpu_concurrency=1`,
`agriculture_worker_geospatial_concurrency=2`,
`agriculture_worker_temporal_concurrency=2`,
`agriculture_worker_fusion_concurrency=2`, and
`agriculture_worker_exports_concurrency=2`. `worker_prefetch_multiplier=1`, late
acknowledgement, and `worker_max_tasks_per_child=5` bound unfair scheduling and
long-lived native-library growth.

## Delivery, retry, and replay

Each stage claim records its queue, task ID, attempt, versioned input checksum,
execution key, output checksum, duration, and business metrics in
`agriculture_analysis_stages`. A duplicate delivery with the same input returns
the persisted result. A changed input is accepted only after an explicit replay
or for a new export request. Continuations are emitted after the stage result is
committed; duplicate continuations are safe because the next claim is
idempotent.

Stages use bounded exponential backoff with jitter and
`agriculture_stage_max_retries`. Exhausted work is routed to
`agriculture-dead-letter`, marks the run replayable, and emits a tenant-scoped
lifecycle event. Operators replay the failed stage through
`POST /agriculture/analysis-runs/{run_id}/stages/{stage_name}/retry`; replay does
not rerun unrelated completed stages.

RGB coordination never polls or reschedules itself. A terminal
`video-analysis` job emits `agriculture.video_inference_completed`; a persisted
per-job signal map deduplicates wakeups and resumes only waiting coordinators.
The six-hour inference wait limit remains a terminal safety gate, checked when a
dependency event arrives or during operational reconciliation.

## Operational signals

Scale first on queue age and stage duration, then confirm database, object
storage, CPU, system memory, and GPU/VRAM headroom. Alert on dead-letter count,
repeated stage failure, inference wait age near the configured limit, output
checksum conflicts, and SSE disconnect rate. Lifecycle SSE is a UI optimization:
durable state remains authoritative and clients retain a slow polling fallback.
Lifecycle events are retained for `workflow_event_retention_days` (30 days by
default); status resources remain the source of truth beyond that replay window.
