# Agriculture production runbook

This runbook is the operational companion for the agriculture API, workers, media storage, analysis queues, and model governance paths.

## Release gates

1. Apply migrations with `alembic upgrade head`; verify the migration revision is recorded.
2. Confirm PostGIS, Redis, object storage, Celery workers, Prometheus, Grafana, and tracing are healthy.
3. Verify the agriculture OpenAPI snapshot with `python backend/scripts/export_agriculture_contract.py && git diff --exit-code -- docs/agriculture-openapi.json`.
4. Run the agriculture backend, frontend, accessibility, contract, security, and E2E suites from `.github/workflows/agriculture-ci.yml`.
5. Do not publish a model without a passing shadow evaluation, dataset/scope metadata, and calibration evidence.

## Media and storage operations

Media keys must be tenant-scoped under `org/{org_id}/...`; raw storage keys are never shown to users. Upload completion validates size, checksum, file signature, and the malware gate before publishing a manifest. Checksum, MIME, scanner-unavailable, or malware failures persist the upload as `quarantined` with a reason in session metadata; operators must inspect the session and remove the temporary object only after retention/legal-hold checks. S3 production must set `AGRICULTURE_MALWARE_SCAN_REQUIRED=true` and provide a reachable ClamAV Unix socket; the built-in EICAR signature check remains an additional deterministic test gate.

Production uses `S3AgricultureStorage` with TLS presigned URLs, server-side encryption, checksum metadata, lifecycle retention, and a backup prefix. Local storage is for development and restore drills only.

Lifecycle actions are tenant-authorized through `/agriculture/media/{media_id}/status`, `/backup`, `/revoke`, and `/restore`. Revocation archives the manifest without deleting its verified artifact; restore can recover from the recorded checksum-verified backup. The retention worker expires only active artifacts whose explicit expiry (or legacy creation cutoff) has elapsed.

## Restore drill

1. Select a non-production media manifest and record its checksum, tenant key, retention state, and lineage IDs.
2. Copy it to the configured backup prefix and verify the checksum.
3. Restore to a new tenant-scoped key, verify the checksum again, and register the derivative as a new immutable artifact.
4. Confirm frame lineage and analysis results still reference the original artifact and that the restored derivative is explicitly versioned.
5. Record the drill result, operator, timestamp, duration, and any data loss in the incident log.

## Worker and queue incidents

- Inspect queue depth, queue age, stage failures, retries, dead letters, worker saturation, and event-loop lag in the agriculture Grafana dashboard.
- Replay only failed/cancelled runs after confirming the input manifest and stage checksum are unchanged.
- A dead-lettered run is not silently retried forever; inspect the recorded error, correct the dependency, then use the replay endpoint.
- Scale CPU, GPU, geospatial, fusion, temporal, and export queues independently.

## Connectivity and flight safety

When the live link is degraded, the frontend shows the connection state and offers reconnect/replay. Flight commands must remain server-authorized and idempotent; never treat an optimistic UI state as proof that a command reached the vehicle. Reconcile runtime events by sequence before resuming operator actions.

## Security response

- A tenant-isolation failure is a release blocker: revoke affected links, preserve audit logs, rotate signing secrets if exposure is possible, and review access logs.
- A quarantined upload is not available to processing or download workflows.
- Revoke/expire signed links through storage lifecycle and export expiry mechanisms; do not share permanent object URLs.
- Rate-limit upload, analysis, and export endpoints and monitor quota rejection metrics.

## Model drift and rollback

Review drift metrics and repeated-failure alerts daily for deployed agriculture models. If drift crosses the configured retraining threshold, block new publication for that task, create a dataset/evaluation record, and roll back to the last validated deployment. Rollback must be audited and followed by a shadow evaluation before republishing.

## SLO starting points

- API error rate: <1% for agriculture routes over 15 minutes.
- P95 analysis queue age: <60 seconds under normal load.
- P95 media upload completion: tracked by file-size class and network region.
- Runtime event gap rate: zero during controlled integration tests; alert on any production gap.
- Signed-link expiry and quarantine transitions: 100% observable in audit/metrics data.
