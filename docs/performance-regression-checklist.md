# Performance regression checklist

Use this checklist before merging changes that touch media processing, agriculture
analysis polling, training, or frontend bundles. Baseline capture:
`docs/performance-baseline.md`.

## Media / video pipeline

- [ ] Run `python3 backend/scripts/benchmarks/run_video_analysis_benchmark.py --fixture` and compare stage seconds vs `docs/benchmarks/performance-baseline-record.json`.
- [ ] Confirm dominant stage unchanged or improvement is intentional and documented.
- [ ] Check Prometheus `media_pipeline_stage_duration_seconds{pipeline="video"}` for unexpected stage spikes (bounded `stage` label only).
- [ ] Verify decode / inference / persistence still separable in job `stage_timings`.

## Agriculture API / UI

- [ ] With analysis page open on a **terminal** run, confirm findings/fusion/actions queries do not poll every 5s.
- [ ] With an **active** run, confirm progress still updates within expected intervals.
- [ ] Compare request count per minute before/after polling or query-key changes.

## Training / inference workers

- [ ] Record GPU utilization (`nvidia-smi dmon`) during representative inference and training jobs.
- [ ] Compare epoch duration and worker saturation metrics when changing dataloader or batch settings.
- [ ] Confirm no unbounded Prometheus labels (no raw run ids / job ids on new metrics).

## Frontend bundles

- [ ] `cd frontend && npm run build && npm run check:bundle-budgets && npm run bundle:size`
- [ ] Compare total MiB and top chunks vs last baseline when adding dependencies.
- [ ] Map routes still lazy-load Google Maps / Cesium (see `docs/fe-001-bundle-budgets.md`).

## Dataset / training materialization

- [ ] Monitor worker RAM during dataset export or epoch materialization changes.
- [ ] Confirm no duplicate full-dataset copies in memory without justification.

## When to block merge

- Regressions >10% on measured stage totals without accepted trade-off note.
- New high-cardinality metrics labels.
- Terminal-state agriculture pages returning to 5s polling loops.

See also: `docs/performance-baseline.md`, `docs/observability.md`.
