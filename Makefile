.PHONY: local-dev docker-dev prod-dev fix check backend-lint backend-typecheck backend-tests backend-integration-tests backend-guardrails backend-quality install-hooks commit-ready
PYTHON ?= python3
BACKEND_QUALITY_PATHS := backend/modules backend/infrastructure backend/entrypoints backend/core backend/tests backend/scripts

local-dev:
	$(MAKE) -f Makefile.local local-dev

docker-dev:
	$(MAKE) -f Makefile.docker docker-dev

prod-dev:
	$(MAKE) -f Makefile.deploy prod-dev

fix:
	ruff check . --fix
	ruff format .
	cd frontend && npx biome check --write .

check:
	$(MAKE) backend-quality
	ruff check .
	ruff format --check .
	cd frontend && npx biome check .
	cd frontend && npx tsc --noEmit

backend-lint:
	$(PYTHON) backend/scripts/check_ruff_baseline.py
	$(PYTHON) -m ruff format --check $(BACKEND_QUALITY_PATHS)

backend-typecheck:
	$(PYTHON) backend/scripts/check_mypy_baseline.py

backend-tests:
	$(PYTHON) -m pytest backend/tests -m "not integration"

backend-integration-tests:
	$(PYTHON) -m pytest backend/tests -m integration

backend-guardrails:
	$(PYTHON) backend/scripts/check_file_sizes.py
	$(PYTHON) backend/scripts/check_backend_boundaries.py
	$(MAKE) PYTHON=$(PYTHON) backend-typecheck
	$(MAKE) PYTHON=$(PYTHON) backend-tests

backend-quality: backend-lint backend-guardrails

install-hooks:
	pre-commit install

commit-ready: fix check
