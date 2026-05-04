.PHONY: local-dev docker-dev prod-dev fix check install-hooks commit-ready

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
	ruff check .
	ruff format --check .
	cd frontend && npx biome check .
	cd frontend && npx tsc --noEmit

install-hooks:
	pre-commit install

commit-ready: fix check