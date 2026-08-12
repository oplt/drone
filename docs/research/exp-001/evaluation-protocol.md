# EXP-001 evaluation protocol

## Goals

Demonstrate **repeatability** of gated spectral indices and **safety** of
prescription/export constraints on fixed offline fixtures before any production
capability label is enabled.

## Fixtures

Located under `backend/scripts/benchmarks/exp001/fixtures/`.

## Pass / fail thresholds

| Check | Gate |
|---|---|
| Spectral validation without panel/calibration | Must `blocked` with explicit reasons |
| NDVI on aligned calibrated fixture | `pass`; mean within ±0.01 of golden |
| Repeat run checksum of index values | Identical across two invocations |
| Prescription without approved rule | `blocked` / `approved_rule_required` |
| Prescription with inspection_only approved rule | Zones only; assumptions include no chemical rates |
| Shapefile export | Contains `.shp/.shx/.dbf/.prj`; WGS84; feature props match fixture |
| ISOXML consumer load | **Not required for research pass**; required for machine GO in ADR |

## Procedure

1. Run `python -m backend.scripts.benchmarks.exp001.run_all`
2. Or `pytest backend/tests/test_exp001_research_suite.py`
3. Attach JSON reports to ADR-003 appendix
4. Agronomy reviewer signs safety-ownership.md before any GO recommendation

## Agronomic validation

Offline fixtures prove **engineering repeatability**, not field agronomy.
Field validation (panel captures on ≥3 fields, agronomist review of index maps)
is a **GO prerequisite** listed in ADR-003 and is intentionally unmet in this
repository slice.
