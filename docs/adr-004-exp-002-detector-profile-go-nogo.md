# ADR-004: EXP-002 detector/tracker profile go/no-go

- Status: **Accepted (NO-GO promotion; retain simplest adequate defaults with provisional note)**
- Date: 2026-08-12
- Tags: `P4` `EXP-002` `research`

## Context

Stand count and weed detection currently default to `small_object_mode=True`
(and stand_count enables ByteTrack) via `default_inference_profile` without an
audited agronomic outcome study. SAHI settings are global; farmer agriculture UX
is already capability-based, but video-analysis diagnostics still expose knobs.

## Experiment

Failure mode: stand count stability (`docs/research/exp-002/failure-mode.md`).
Offline fixture harness compared profiles A–D
(`backend/scripts/benchmarks/exp002`).

## Measured result (fixture report)

On the locked synthetic pack, **profile A (standard)** meets count_error and
fragmentation gates with the lowest cost proxy. Profile D (current default
combo) improves small-object recall but **fails** count_error and/or
fragmentation gates on the representative fixture (see eval report). Therefore
**no advanced profile is promoted** as a versioned production release profile.

## Decision

| Item | Decision |
|---|---|
| Promote SAHI+track as audited release profile | **NO-GO** |
| Add new tracker adapters | **NO-GO** (avoid config debt) |
| Farmer UX | Remain capability-based (no detector brand) |
| Video-analysis knobs | Diagnostics/advanced only; not agriculture default |
| `default_inference_profile` | Revert stand_count/weed to **standard baseline** (A) until a field GO study promotes a versioned profile on a capability release |
| Losing experiment configs | Do not add alternate SAHI size/overlap release fields |

## Consequences

- Capability releases may still override `inference_profile` explicitly after a
  future GO study; defaults stay conservative.
- ML-005 map50 gates remain; EXP-002 agronomic gates are separate and required
  for profile promotion.
- Revisit with real GPU corpus + GT plant counts (PERF-001 hardware profile).

## Rollback

Defaults return to standard inference; prior provisional SAHI-on defaults are
documented here as non-promoted experiment assumptions.
