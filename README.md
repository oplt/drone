# Drone Operations Platform

Ths app is a full-stack drone operations platform for planning, launching, and monitoring autonomous missions from a single operator console. This repository combines a FastAPI backend that talks to vehicles, telemetry, video, mapping, and alerting services with a React dashboard for field teams.

The product direction is agronomy-first, but the codebase also includes warehouse scanning, indoor warehouse exploration, private patrol, and animal monitoring workflows.

## What the project does

- Plan and run waypoint, grid, photogrammetry, private patrol, warehouse scan, and indoor exploration missions.
- Stream live telemetry, mission lifecycle updates, and video into a browser-based dashboard.
- Run configurable preflight checks before mission start.
- Manage fields, geofences, warehouse maps, docks, settings, and operator-facing alerts.
- Process photogrammetry jobs through a queued pipeline with WebODM and publish mapping assets.
- Support ML-assisted patrol workflows and websocket event broadcasting.

## Architecture at a glance

### Frontend

- React 19 + TypeScript + Vite
- Material UI dashboard
- Google Maps + Cesium mission views
- TanStack Query for data fetching

### Backend

- FastAPI application with websocket support
- SQLAlchemy async models and repository layer
- Drone control/orchestration modules built around MAVLink/DroneKit-style integrations
- MQTT, video streaming, alerting, and mission preflight services
- Celery + Redis queue path for heavy photogrammetry processing

## Repository layout

```text
frontend/   React operator console and public landing pages
backend/    FastAPI API, mission logic, telemetry, auth, data models, workers
docs/       Architecture notes and mission design docs
```

Architecture decisions live in `docs/adr/`. Runtime inventories live in
`docs/architecture/`. Start with
`docs/adr/ADR-001-canonical-live-ops-runtime-architecture.md` and
`docs/adr/ADR-002-canonical-runtime-envelope-schemas.md`,
`docs/architecture/runtime-envelope-schemas-v1.md`,
`docs/architecture/live-ops-runtime-path-inventory.md` plus
`docs/architecture/live-ops-hot-path-current-state.md` for the current
live-operations boundary, canonical schema contract, path map, and hot-path
drawing.

Notable backend areas:

- `backend/api/`: HTTP and websocket routes
- `backend/flight/`: mission definitions, indoor navigation, preflight checks
- `backend/services/photogrammetry/`: mapping ingest, storage, WebODM integration
- `backend/services/warehouse/`: warehouse capture and post-processing flows
- `backend/ml/`: patrol/anomaly runtime
- `backend/tasks/`: Celery app and photogrammetry worker tasks

## Core workflows

### Mission control

The platform exposes multiple mission types, including field routes, photogrammetry surveys, private patrol, warehouse scan missions, and indoor warehouse exploration from a docked start position.

### Live operations

The dashboard is built for operator-in-the-loop control with mission status, telemetry websockets, map overlays, preflight results, and live video panels.

### Mapping

Photogrammetry jobs are staged through the API and processed asynchronously by Celery workers. The pipeline is designed to publish orthomosaics, terrain products, mesh outputs, and mapping assets for later retrieval.

### Warehouse and indoor autonomy

The warehouse subsystem includes warehouse map management, mission defaults, scanned-map asset handling, and an indoor exploration mission that does not depend on GPS. See `docs/indoor_warehouse_exploration_mission.md` for the detailed mission design.

## Local development

This repository is an application repo, not a packaged library, so the main goal locally is to run the API, dashboard, and optional worker services together.

### Prerequisites

- A recent Python 3 environment
- Node.js and npm
- PostgreSQL for the application database
- Redis if you want to run queued photogrammetry jobs
- Optional external services depending on the workflow: Google Maps, WebODM, MQTT broker, camera stream source, Raspberry Pi companion, and ML assets

### 1. Install backend dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
```

### 3. Configure environment variables

The repo already contains `backend/.env` and `frontend/.env`. Review and update them for your environment before running the stack.

Common backend configuration groups include:

- database and auth: `DATABASE_URL`, `JWT_SECRET`, `SETTINGS_VAULT_KEY`
- vehicle connectivity: `DRONE_CONN`, `DRONE_CONN_MAVPROXY`, `HEARTBEAT_TIMEOUT`
- maps and UI integrations: `GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_JAVASCRIPT_API_KEY`
- optional services: `MQTT_*`, `LLM_*`, `RASPBERRY_*`, `ML_*`

Common frontend configuration keys include:

- `VITE_API_BASE_URL`
- `VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY`
- `VITE_GOOGLE_MAPS_MAP_ID`
- `VITE_CESIUM_ION_TOKEN` (optional, for Cesium-backed views)

### 4. Run the backend API

```bash
uvicorn backend.api.api_main:app --reload
```

The API starts the FastAPI app, initializes the database connection, loads runtime settings, and exposes a health endpoint at `GET /health`.

### 5. Run the frontend

```bash
cd frontend
npm run dev
```

By default, the frontend expects the API at `http://localhost:8000`.

### 6. Run the optional photogrammetry worker

If you want queued mapping jobs to process instead of just being enqueued, start Redis and a Celery worker:

```bash
celery -A backend.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=photogrammetry \
  --hostname=photogrammetry@%h
```

See `backend/tasks/README.md` for worker deployment details, required environment variables, and WebODM/toolchain expectations.

## API and feature areas

Some of the main route groups in the backend are:

- `/tasks` for mission creation, preflight, and mission lifecycle operations
- `/mapping` for photogrammetry jobs and mapping assets
- `/warehouse` for warehouse maps, mission defaults, scans, and exploration launches
- `/api/ml` for patrol ML runtime controls

Additional modules cover auth, analytics, geofences, fields, settings, alerts, video, and telemetry websockets.

## Notes for contributors

- The backend includes Alembic files in `backend/alembic/`, although the app also initializes tables on startup.
- Photogrammetry is intentionally offloaded to worker processes rather than the API server.
- Some UI copy is agronomy-specific, while the backend supports broader drone operations use cases.
