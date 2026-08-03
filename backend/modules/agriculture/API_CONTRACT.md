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
