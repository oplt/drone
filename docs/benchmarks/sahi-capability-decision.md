# Capability-specific SAHI decision

TASK 3.6 keeps sliced inference controlled exclusively by the immutable
agriculture inference profile. The worker never infers SAHI use from image
dimensions, labels, model names, or detected object sizes. A persisted profile
and its legacy job fields must agree or the job fails before model loading.

## Current decisions

| Capability profile | SAHI | Evidence | Decision |
|---|:---:|---|---|
| general anomaly | off | No capability-specific field benchmark | Retain standard baseline |
| weed detection | off | No audited field accuracy/runtime result | Retain standard baseline |
| stand count | off | EXP-002 profile C: recall 1.0, count error 0.40, runtime 2.8x | NO-GO |
| visible crop-health anomaly | off | No capability-specific field benchmark | Retain standard baseline |
| canopy cover | off | No capability-specific field benchmark | Retain standard baseline |
| row detection | off | No capability-specific field benchmark | Retain standard baseline |
| standing water | off | No capability-specific field benchmark | Retain standard baseline |

The deterministic EXP-002 fixture reports unchanged small-object recall for
SAHI profile C, but count error rises from 0.00 to 0.40 and runtime from 1.0 to
2.8 relative to the standard profile. It therefore fails the registered count,
runtime, and cost gates. These fixture results are not a substitute for a real
GPU field corpus; they are sufficient to prevent an unsupported default.

## Promotion rule

Enable `sahi_enabled` only in a new capability release profile whose locked
model/corpus report demonstrates acceptable accuracy, small-object recall, and
runtime for that capability. The new profile digest then changes analysis
fingerprints and prevents reuse across standard and sliced inference.

Run the current decision fixture with:

```sh
.venv/bin/python backend/scripts/benchmarks/exp002/run_all.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p pytest_asyncio.plugin backend/tests/test_exp002_research_suite.py -q
```
