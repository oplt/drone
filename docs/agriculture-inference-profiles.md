# Agriculture inference profiles

Agriculture model releases use capability-specific, immutable inference profiles.
The initial `agriculture-inference-profile.v1` profiles intentionally retain the
previous runtime behavior until representative accuracy and throughput benchmarks
justify changing a capability default.

## Profile contract

Each model-backed capability resolves a complete profile containing:

- `profile_id`, `profile_version`, `capability_id`, and a SHA-256 `profile_digest`
- `sample_fps`, `image_size`, `confidence_threshold`, `batch_size`, and
  `precision_mode`
- explicit SAHI enablement, slice dimensions, overlap ratios, and match threshold
- tracking enablement and tracker type

Profiles are validated before a capability release is activated. Image and slice
dimensions must be multiples of 32, numeric values are bounded by the video API
contract, and a profile cannot be used for a different capability.

## Reproducibility and reuse

The resolved profile is stored in the capability release snapshot and therefore in
the agriculture run's `model_versions` input manifest. The complete manifest is
covered by `AgricultureAnalysisRun.input_checksum`; changing either profile identity
or any execution value produces a different analysis fingerprint.

Every submitted video job also persists the profile. Completed inference is reused
only when source checksum, model version/checksum, capability release, telemetry
contract, and the complete profile recorded by both the job and agriculture link
match. Legacy jobs without a complete profile are deliberately not reused because
their execution identity cannot be proven.

## Baseline defaults

The registry defines separate identities for general anomaly, weed detection, stand
count, visible crop-health anomaly, canopy cover, row detection, and standing water.
Their v1 execution values remain the previous defaults: 1 FPS, image size 640,
confidence 0.35, standard full-frame inference, and the configured device-aware
`VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE`. Precision remains `fp32`; `fp16` is an
explicit profile opt-in and fails closed unless the selected CUDA device supports
it. Existing SAHI environment defaults are frozen into the profile even while SAHI
is disabled, so enabling it later is explicit and reproducible.

The capability decision matrix and current accuracy/runtime evidence are recorded
in `docs/benchmarks/sahi-capability-decision.md`.
