# Agriculture worker and storage operations

Run one worker pool per queue. GPU queues must run in GPU-enabled containers and
must never be consumed by API processes:

```text
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-ingest -c 4
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-quality -c 2
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-rgb-inference -c 1
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-segmentation -c 1
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-geospatial -c 2
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-temporal -c 2
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-fusion -c 2
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-exports -c 2
celery -A backend.entrypoints.workers.celery_app worker -Q agriculture-dead-letter -c 1
```

Stage jobs are keyed by run input checksum plus model, calibration and parameter
manifest. Completed stages reject conflicting replay checksums. Retries use bounded
exponential jitter; exhausted jobs record replayable dead-letter metadata. Operator
replay uses `POST /agriculture/analysis-runs/{id}/replay`.

Production object storage requirements:

- private bucket, blocked public access and least-privilege tenant-prefix policies;
- TLS-only endpoints and presigned GET access;
- SSE-S3 (`AES256`) or deployment-managed KMS encryption;
- object versioning, lifecycle expiration, checksum metadata and legal-hold exclusion;
- cross-region/versioned backup according to deployment RPO/RTO.

Local backup/restore uses `AgricultureStorage.backup` and `restore`; both verify
SHA-256 before publishing the restored target. Run the backup/restore contract test
after storage-driver or infrastructure changes. Retention cleanup is hourly and marks
database records expired after object deletion. `legal_hold` assets are never selected.

Prometheus rules live in `infra/observability/prometheus/rules`; Grafana provisions
the `Agriculture Operations` dashboard. Treat dead letters, repeated failures and low
georeference rate as release-blocking alerts.
