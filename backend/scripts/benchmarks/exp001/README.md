# EXP-001 offline fixtures

Immutable research inputs for spectral gates, prescription safety, and shapefile
export conformance. Run:

```bash
.venv/bin/python backend/scripts/benchmarks/exp001/run_all.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin backend/tests/test_exp001_research_suite.py -q
```

See `docs/research/exp-001/` and `docs/adr-003-exp-001-multispectral-prescription-go-nogo.md`.
