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
