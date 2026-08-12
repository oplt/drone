.PHONY: start local-dev warehouse docker-dev prod-dev fix check backend-lint backend-typecheck backend-tests backend-integration-tests backend-test-env-up backend-test-env-down backend-guardrails backend-quality backend-p2-static-gates backend-p4-research-gates frontend-quality frontend-tests frontend-e2e install-hooks commit-ready security-scan
.PHONY: kill-dev kill-ports kill-workers kill-warehouse kill-ros-bridge stop-bridge reset-dev reset-frontend-cache
.PHONY: start-maple stop-maple observability-status start-observability-stack stop-observability-stack local-dev-no-observability


PYTHON ?= python3
BACKEND_QUALITY_PATHS := backend/modules backend/infrastructure backend/entrypoints backend/core backend/tests backend/scripts

start: local-dev

local-dev:
	$(MAKE) -f Makefile.local local-dev

warehouse:
	$(MAKE) -f Makefile.local warehouse

docker-dev:
	@test -f Makefile.docker || { echo "Makefile.docker not found. Use 'make start' or add Makefile.docker."; exit 1; }
	$(MAKE) -f Makefile.docker docker-dev

prod-dev:
	@test -f Makefile.deploy || { echo "Makefile.deploy not found. Use 'make start' or add Makefile.deploy."; exit 1; }
	$(MAKE) -f Makefile.deploy prod-dev

fix:
	ruff check . --fix
	ruff format .
	cd frontend && npx biome check --write .

check:
	$(MAKE) backend-quality
	cd frontend && npx biome check .
	cd frontend && npx tsc --noEmit

backend-lint:
	$(PYTHON) backend/scripts/check_ruff_baseline.py
	$(PYTHON) -m ruff format --check $(BACKEND_QUALITY_PATHS)
	# AGR-001: keep Agriculture free of undefined-name/import regressions without
	# requiring a repository-wide formatting cleanup.
	$(PYTHON) -m ruff check --select F821,F401 backend/modules/agriculture

backend-typecheck:
	$(PYTHON) backend/scripts/check_mypy_baseline.py

backend-tests:
	$(PYTHON) backend/scripts/run_backend_tests.py --skip-migrations

backend-integration-tests:
	$(PYTHON) backend/scripts/run_backend_tests.py --integration --wait-db

security-scan:
	$(PYTHON) backend/scripts/check_secrets.py

backend-test-env-up:
	docker compose -f docker-compose.test.yml up -d postgres redis minio

backend-test-env-down:
	docker compose -f docker-compose.test.yml down -v

backend-guardrails:
	$(MAKE) PYTHON=$(PYTHON) security-scan
	$(PYTHON) backend/scripts/check_file_sizes.py
	$(PYTHON) backend/scripts/check_backend_boundaries.py
	$(PYTHON) backend/scripts/check_module_ports.py
	$(MAKE) PYTHON=$(PYTHON) backend-typecheck
	$(MAKE) PYTHON=$(PYTHON) backend-tests

backend-p2-static-gates:
	$(PYTHON) backend/scripts/check_p2_static_gates.py

backend-p4-research-gates:
	$(PYTHON) backend/scripts/check_p4_research_gates.py
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest -p pytest_asyncio.plugin backend/tests/test_exp001_research_suite.py backend/tests/test_exp002_research_suite.py backend/tests/test_p4_research_gates.py -q

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

kill-dev kill-ports kill-workers kill-warehouse kill-ros-bridge stop-bridge reset-dev reset-frontend-cache start-maple stop-maple observability-status start-observability-stack stop-observability-stack local-dev-no-observability:
	$(MAKE) -f Makefile.local $@
