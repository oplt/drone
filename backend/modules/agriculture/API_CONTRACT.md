# Agriculture API contract v1

All `/agriculture` responses carry `X-Agriculture-Schema-Version: agriculture.v1`.
Successful resources use typed OpenAPI schemas; cursor lists use the stable envelope
`{schema_version, items, next_cursor, total}`. Errors use the application envelope
`{error: {code, message, details}, request_id}` with machine-readable codes.

Queued mission starts, analysis work, replays and comparisons return HTTP 202.
Immutable layers and signed artifacts return quoted ETags and private immutable cache
headers. Clients must send `Idempotency-Key` for telemetry batches; manifest ingestion
includes an idempotency key and canonical JSON SHA-256 checksum in its body.

Compatibility aliases remain available (`/flights/{id}/compare`,
`/flights/{id}/comparisons`, and `/fields/{id}/temporal-timeline`) while clients move
to field-scoped comparisons and `/comparisons/{id}` resources.

Request examples are published in the OpenAPI component schemas for telemetry,
media, manifests, comparison, review and export payloads. Mission-start payloads reuse
the documented `MissionCreateIn` schema.

Phase 5 analytics add a research-only crop/weed segmentation evaluation endpoint
at `/analysis-runs/{run_id}/analytics/segmentation-experiment`. Operational
stand-gap, plant-spacing, and weed-density outputs use the existing immutable
layer and observation contracts. Calibrated fusion accepts `ndvi`, `gndvi`, and
`ndre`; thermal results require ambient environmental context. The full safety
and applicability rules are documented in `docs/agriculture-analytics-phase5.md`.

Phase 6 lifecycle streams are available at
`GET /agriculture/analysis-runs/{run_id}/events` and
`GET /vision/projects/{project_id}/training-events`. They use `text/event-stream`,
durable numeric event IDs, browser `Last-Event-ID` replay, and organization scope
(or creator scope for non-organization resources). Clients must retain polling as
a fallback. Analysis execution uses versioned, independently replayable Celery
stages; export creation returns HTTP 202 with a queued `ExportOut`, and clients
observe it until `ready` or `failed`. Queue and worker guidance is documented in
`docs/agriculture-stage-scaling.md`.
