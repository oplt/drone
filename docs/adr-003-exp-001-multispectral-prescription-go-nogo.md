# ADR-003: EXP-001 multispectral & prescription go/no-go

- Status: **Accepted (NO-GO / DEFER production)**
- Date: 2026-08-12
- Tags: `P4` `EXP-001` `research`

## Context

Competitors advertise multispectral indices and machine prescriptions. This
repository’s audited production path is RGB/video with human-approved inspection
actions. Scaffolding exists for spectral gates and prescription drafts, but
customer hardware validation, field agronomy repeatability, and ISOXML/machine
consumer contracts are not proven.

## Decision

**Do not enable production capability labels** for multispectral stress mapping
or machine prescriptions at this time.

| Track | Decision |
|---|---|
| Offline research fixtures + eval suite | **GO** (shipped under `docs/research/exp-001` and `backend/scripts/benchmarks/exp001`) |
| Production `multispectral_*` capability id | **NO-GO** |
| Production treatment/rate maps | **NO-GO** |
| Inspection-only approved exports (existing P5) | **KEEP** (already gated) |
| ISOXML / Task Controller integration | **DEFER** until a named consumer load test passes |

## Evidence summary

- Spectral gates correctly block missing panel/calibration (`test_exp001_research_suite`)
- NDVI/GNDVI repeatability holds on synthetic fixtures (engineering only)
- Prescription safety blocks unapproved rules and rate generation
- Shapefile zip members/CRS validated offline; **not** a machine consumer proof
- Field multi-farm agronomic validation: **not available** in-repo

## Consequences

- `capabilities.py` must not add multispectral/prescription product ids
- Roadmap readiness entries for MS/prescription remain `research_blocked`
- Marketing must not claim general NDVI/prescription availability
- Capture presets may inventory MS sensors for planning without enabling MS analysis products
- Revisit when: ≥3 field panel datasets, agronomist sign-off, and one real downstream consumer validation exist

## Ownership

See `docs/research/exp-001/safety-ownership.md`.
