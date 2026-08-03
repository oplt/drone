# Agriculture foundation compatibility

Migration `w9d6e7f8a9b0` is additive. Existing `grid` missions remain generic
unless they include both `field_id` and the explicit `agriculture` profile; their
video-analysis behavior is unchanged. `MissionRuntime.mission_params` now stores
the submitted payload for every new mission, which is backward-compatible with
older rows containing `{}`.

Rollback is safe before agriculture rows are used: `alembic downgrade
w9d6e7f8a9b0^` removes the agriculture tables. Before rollback in an environment
with captured agriculture data, export manifests/telemetry and remove dependent
flight rows first; legacy video assets are not deleted by the migration.

Release 1 analysis tables are additive migration `x1a2b3c4d5e6f`; downgrade it
first when rolling back stages, quality, observations, layers, or baselines.

Release 2 temporal/review/learning tables are additive migration `y2b3c4d5e6f7a`;
downgrade it first before removing comparison, audit, annotation, dataset, or
model-report records.

Release 3 sensor/fusion tables are additive migration `z3c4d5e6f7a8b`; downgrade
it first before removing spectral bands, external readings, calibrations, or
fusion results.

Release 4 crop insight, growth, harvest-label, and yield tables are additive
migration `a4d5e6f7a8b9c`; downgrade it first before removing crop-risk,
growth, harvest, or forecast records. Crop-specific model output requires a
deployed model plus validation thresholds and remains a candidate until review.
Yield remains not applicable without two flights and two quality harvest labels.

Release 5 action, prescription, export, and governance tables are additive
migration `b5e6f7a8b9c0d`; downgrade it first before removing inspection
actions, agronomy rules, prescription drafts, export artifacts, or access
audits. Export files are local/S3-port artifacts with 24-hour metadata expiry
and short-lived signed download URLs; regenerate after expiry.

Release 6 agriculture assistant runs are additive migration `c6f7a8b9c0d1`;
downgrade it first before removing assistant outputs, deterministic findings,
citations, or review records. Assistant context excludes raw media, secrets,
unconfirmed observations, and untrusted instructions. Provider failures produce
an auditable rules-only fallback; no assistant output can execute treatment,
chemical, fertilizer, or flight-control actions.
