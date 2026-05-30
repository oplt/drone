.PHONY: local-dev local-dev-warehouse docker-dev prod-dev fix check backend-lint backend-typecheck backend-tests backend-integration-tests backend-guardrails backend-quality frontend-quality frontend-tests frontend-e2e install-hooks commit-ready
PYTHON ?= python3
BACKEND_QUALITY_PATHS := backend/modules backend/infrastructure backend/entrypoints backend/core backend/tests backend/scripts

local-dev:
	$(MAKE) -f Makefile.local local-dev

local-dev-warehouse:
	$(MAKE) -f Makefile.local local-dev-warehouse

docker-dev:
	@test -f Makefile.docker || { echo "Makefile.docker not found. Use 'make local-dev' or add Makefile.docker."; exit 1; }
	$(MAKE) -f Makefile.docker docker-dev

prod-dev:
	@test -f Makefile.deploy || { echo "Makefile.deploy not found. Use 'make local-dev' or add Makefile.deploy."; exit 1; }
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

frontend-quality:
	cd frontend && npm run lint:ci
	cd frontend && npm run check:arch
	cd frontend && npm run build

frontend-tests:
	cd frontend && npm run test

frontend-e2e:
	cd frontend && npm run test:e2e:install
	cd frontend && npm run test:e2e

install-hooks:
	pre-commit install

commit-ready: fix check
