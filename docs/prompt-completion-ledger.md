# Prompt completion ledger

Maps `prompt.txt` incomplete items (2026-08-12 audit) to delivery status.

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | P0 CI failing (env, lint, Postgres) | COMPLETE | CI sets `DATABASE_URL`/`SETTINGS_VAULT_KEY`, PostGIS service, alembic upgrade, migration test; ESLint regressions fixed; expanded FE unit tests |
| 2 | P0/P1 Perf harness scaffolding | COMPLETE (fixture parity) | Real confidence/box parity comparisons on fixture detections; live GPU path still exits 2 by design until hardware corpus GO (defaults stay off) |
| 3 | P1 Vision storage lifecycle | COMPLETE | Eval artifacts + dataset image/thumbnail `VisionStorageObject`s, dual-read, staged reconciler; migration `j3k4l5m6n7o8` |
| 4 | P1 reanalysis_required bug | COMPLETE | `capture_metadata_revision` on asset+job; clear only on successful complete with matching revision |
| 5 | P1 Module boundaries | COMPLETE | `storage_path` removed from `VideoSourceRef`; port media resolve; telemetry matcher shared; vision↛`video_analysis.service` |
| 6 | P1 Release policy generic | COMPLETE | Non-empty `CAPABILITY_METRIC_OVERRIDES`; frozen inference profile in contract; activate prefers contract |
| 7 | P1/P2 pHash prefix miss | COMPLETE | `prefix_probe_keys` multi-probe neighboring buckets + tests |
| 8 | P2 Unbounded `list_detections` | COMPLETE | Paged/bbox-filtered port + SQL class aggregates; Agriculture pages |
| 9 | P2 CLEAN-001 schema drop | DEFERRED | Explicit: run inventory on prod DBs before destructive migration |

Alembic head: `j3k4l5m6n7o8`.
