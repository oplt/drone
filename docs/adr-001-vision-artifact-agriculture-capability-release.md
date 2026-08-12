# ADR-001: Vision owns model artifacts; Agriculture owns capability releases

- Status: accepted
- Date: 2026-08-12

## Decision

`vision_model_versions` is the sole durable owner of a trained model artifact,
its storage URI, checksum, dataset and training provenance, evaluation results,
version identity, and candidate/production/archive lifecycle.

Agriculture does not copy those facts. An
`agriculture_capability_releases` record references one production Vision model
version and owns only the agronomic policy needed to use it: canonical
capability ID, tenant/user scope, crop and sensor applicability, inference
profile, thresholds, approval, and effective/retirement dates. One partial
unique database index permits only one active release per scope and capability.

Analysis runs freeze the resolved release, Vision version/checksum, and
inference profile. Each model-backed capability is also linked to the exact
Video Analysis job and source video used. Agriculture consumes typed Video
Analysis contracts, not Video ORM records.

## Legacy data

`agriculture_model_versions` is read-only migration inventory. Upgrade links a
legacy row only when its artifact URI identifies exactly one released Vision
version. Every ambiguous or unmatched row is marked `quarantined`; it is never
silently deleted or selected for new analysis. Legacy write/publish endpoints
return `410 LEGACY_MODEL_REGISTRY_READ_ONLY`. Destructive removal is deferred
until operators have resolved quarantined records.

## Consequences

- Deploying an eligible Vision version transactionally activates its
  Agriculture capability release and retires the prior release.
- Archiving a Vision version retires its active Agriculture release.
- Readiness and analysis use a single indexed release-to-Vision join.
- Rollback of this migration restores the legacy schema before any destructive
  cleanup; model artifacts remain untouched.
