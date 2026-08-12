# EXP-002 evaluation protocol

## Profiles compared (fixed synthetic corpus)

| ID | small_object_mode | tracking_enabled | Notes |
|---|---|---|---|
| A | false | false | Standard baseline |
| B | false | true | Tracking only |
| C | true | false | SAHI-like dense proposals |
| D | true | true | Current stand_count default |

## Fixtures

`backend/scripts/benchmarks/exp002/fixtures/` — immutable JSON with GT counts,
GT boxes, and per-profile predicted boxes/tracks (deterministic offline
simulation of detector behavior). Real GPU video parity is a follow-on when
hardware corpus is attached; this suite proves the **metric + promotion gate**
machinery.

## Procedure

1. `python -m backend.scripts.benchmarks.exp002.run_all`
2. `pytest backend/tests/test_exp002_research_suite.py`
3. Attach report JSON to ADR-004

## Promotion rule

Promote profile X only if it beats A on agronomic count_error **and** meets all
gates. Otherwise keep simplest adequate profile and record non-promotion.
