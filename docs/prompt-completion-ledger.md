# Prompt completion ledger

Maps remaining incomplete work after P0–P4 against the agriculture roadmap in
`tasks.txt` (working-tree `prompt.txt` had been overwritten with an unrelated
Troop/workforce audit and was restored to the agriculture audit source).

Status: **COMPLETE** | **DEFERRED**.

| # | Item | Status | Files / tests | Notes |
|---|------|--------|---------------|-------|
| 1 | VID-002 scalable aggregates + FE | COMPLETE | SQL `aggregate_detections`; FE `getDetectionAggregates`, `DetectionTimeline` buckets, window detail fetch; `test_video_detection_scale.py` | Timeline/summary no longer require loading every detection. |
| 2 | ARCH-001 module boundaries | COMPLETE | Vision→Video ports; `check_module_ports.py` | |
| 3 | ML-005 release policy | COMPLETE | `release_policy.py`; `test_release_policy.py` | |
| 4 | ML-006 leakage / dedupe | COMPLETE | Dataset-wide pHash + training quality gate | |
| 5 | EVD / FE polish | COMPLETE | Evidence refs, journey UI | |
| 6 | STOR-001 evidence + vision weights | COMPLETE | Video crops staged→final + orphan reconcile; Vision `vision_storage_objects` + `ModelVersion.storage_object_id`; migration `i2j3k4l5m6n7`; `test_stor_vid_provenance.py`, `test_vision_storage_object.py` | Cross-module video StorageObject reuse intentionally avoided (ADR-002). |
| 7 | SEC-001 query-token media | COMPLETE | Cookie/header auth only | |
| 8 | PERF-001/002 harness | COMPLETE (harness) | Flags remain OFF until measured GO | |
| 9 | CLEAN-001 | COMPLETE (safe slice) | Schema drop deferred pending prod inventory | |
| 10 | TEST-001 PR CI | COMPLETE (PR gates) | Expanded focused pytest; Playwright/Postgres service jobs deferred | |
| 11 | UX-001 + VID-003 capture UI | COMPLETE | Field wizard polish; `CaptureMetadataEditor` PATCH capture-metadata | |

## Still deferred (explicit)

- CLEAN-001 destructive `instance_segmentation` schema drop
- PERF-002 production GO before enabling decode-stride/batch defaults
- TEST-001 Playwright + Postgres/PostGIS migration jobs on every PR
- Full STOR retention/legal-hold UX and backup restore drill automation in PR CI
