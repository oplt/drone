# EXP-002 offline fixtures

Stand-count profile comparison corpus (synthetic, deterministic). Run:

```bash
.venv/bin/python backend/scripts/benchmarks/exp002/run_all.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin backend/tests/test_exp002_research_suite.py -q
```

See `docs/research/exp-002/` and `docs/adr-004-exp-002-detector-profile-go-nogo.md`.
