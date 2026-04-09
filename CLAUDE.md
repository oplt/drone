# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run API server
uvicorn backend.api.api_main:app --reload

# Type checking
mypy backend/

# Lint
ruff check --fix .
flake8 backend/

# Database migrations
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini revision --autogenerate -m "description"

# Celery photogrammetry worker (requires Redis)
celery -A backend.tasks.celery_app:celery_app worker --loglevel=INFO --queues=photogrammetry --hostname=photogrammetry@%h
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Dev server at http://localhost:5173
npm run build    # Production build (includes tsc -b type check)
npm run lint     # ESLint
```

## Architecture

### Request flow

```
[React Dashboard] → HTTP/WebSocket → [FastAPI Routes] → [Mission/Service Logic]
                                                               ↓
                                              [Orchestrator (live-ops hub)]
                                                               ↓
                                   [MAVLink Drone] + [Video] + [MQTT] + [DB/Redis]
```

### Orchestrator (`backend/drone/orchestrator.py`)

The **single source of truth for all live-ops state**. Owns the MAVLink connection, mission lifecycle, video health, and outbound event broadcasts. The API never writes telemetry or flight events directly — everything routes through the Orchestrator. Instantiated as a singleton in `backend/main.py` via `_build_orchestrator()` and injected into the FastAPI lifespan in `backend/api/api_main.py`.

Key methods: `run_mission()`, `start_live_telemetry()`, `emit_mission_lifecycle_event()`, `record_persisted_event()`.

### Missions (`backend/flight/missions/`)

All mission types subclass the `Mission` base and implement `plan()` (preview/validate) and `execute()`. Mission types: `GridMission`, `WaypointsMission`, `PrivatePatrolMission`, `PhotogrammetryMission`, `WarehouseScanMission`, `WarehouseExplorationMission` (GPS-free, dock-relative).

### Preflight (`backend/flight/preflight_check/`)

`PreflightOrchestrator` runs modular checks (GPS fix, satellites, compass, battery, EKF, HDOP, home distance) before any mission executes. Results use `CheckStatus` (PASS/WARN/FAIL) and are persisted to the database.

### Canonical event envelopes (`backend/runtime/`)

All live-path data uses versioned envelope schemas defined in `docs/architecture/runtime-envelope-schemas-v1.md`:
- `TelemetryEnvelopeV1` — continuous sensor data
- `FlightEventEnvelopeV1` — discrete incidents (severity-tagged)
- `MissionLifecycleEnvelopeV1` — mission state transitions

Architecture decisions for the live-ops boundary live in `docs/adr/ADR-001` and `ADR-002`.

### Services (`backend/services/`)

| Service | Responsibility |
|---|---|
| `photogrammetry/` | Image staging, WebODM integration, COG/tile/mesh generation |
| `patrol/` | YOLO detector, motion detection, loitering alerts, evidence storage |
| `warehouse/` | Scanned map assets, dock-relative navigation |
| `alerts/` | Rules engine — battery, signal, wind, geofence breaches |
| `animal_farm/` | Herd monitoring, isolation detection |

Photogrammetry processing is intentionally offloaded to Celery workers (separate from the API process). See `backend/tasks/README.md` for worker toolchain requirements.

### Database (`backend/db/`)

SQLAlchemy 2.0 async with asyncpg. Key models: `Flight`, `FlightEvent`, `TelemetryRecord`, `PatrolDetection`, `MappingJob`. Repository pattern in `backend/db/repository/`. Alembic manages migrations, but the app also initializes tables on startup.

### API routes (`backend/api/routes/`)

Main groups: `/tasks` (mission lifecycle), `/mapping` (photogrammetry jobs and assets), `/warehouse`, `/api/ml` (patrol ML controls), plus auth, analytics, geofences, fields, settings, alerts, video, telemetry WebSocket.

### Frontend (`frontend/src/`)

React 19 + TypeScript + Vite. Pages are lazy-loaded via React Router. TanStack Query manages all server state. Maps use Google Maps API and optionally Cesium.js for 3D. Vite dev server proxies `/api` and `/ws` to the backend.

### MAVLink layer (`backend/runtime/mavlink.py`)

Low-level MAVLink helpers used by the Orchestrator. Do not import MAVLink primitives directly in routes or services — go through the Orchestrator.

### Celery tasks (`backend/tasks/`)

`celery_app.py` defines the Celery app (broker = Redis). `photogrammetry_tasks.py` contains the long-running WebODM pipeline task. These run in a separate worker process — not in the API process. See `backend/tasks/README.md` for toolchain requirements (GDAL, node-odm, etc.).

## Tests

There are no project-level tests currently. The `.venv` contains third-party test files that are not project tests. When adding tests, place them under `backend/tests/` and use `pytest`.

## Key config files

- `backend/.env` — DB URL, drone connection string, API keys, service endpoints
- `backend/config.py` — `BootstrapSettings` / `RuntimeSettings` Pydantic classes
- `frontend/.env` — `VITE_API_BASE_URL`, Google Maps keys, Cesium token
- `frontend/vite.config.ts` — Vite plugins, dev proxy rules

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **drone_app** (4698 symbols, 14204 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/drone_app/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/drone_app/context` | Codebase overview, check index freshness |
| `gitnexus://repo/drone_app/clusters` | All functional areas |
| `gitnexus://repo/drone_app/processes` | All execution flows |
| `gitnexus://repo/drone_app/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
