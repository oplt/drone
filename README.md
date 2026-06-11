# Drone Operations Platform

A full-stack drone mission control application with a FastAPI backend, React operator dashboard, and optional ROS 2 / Gazebo simulation integration. The platform supports mission planning and execution, live telemetry over WebSockets, warehouse indoor scanning with live 3D map streaming, video/camera runtime, photogrammetry job orchestration, and geospatial workflows.

The codebase is under active development. Core APIs, UI modules, and simulation bridges exist, but hardware integrations, ROS/Gazebo stacks, and some domain workflows require environment-specific setup and validation before field use.

---

## Key Features

- **Mission operations** — create, run, monitor, and resume missions (waypoint, grid survey, controlled flight, private patrol, warehouse scan)
- **Live telemetry** — WebSocket broadcasting of mission and vehicle events (`/ws/telemetry`)
- **Warehouse scanning** — indoor scan missions, preflight checks, dock/map management, scanned-map persistence
- **Live 3D mapping** — chunked point-cloud ingest, WebSocket stream, and Three.js viewer for warehouse flights
- **ROS / Gazebo bridge** — `ros2_ws` package bridges Gazebo Sim sensor topics into ROS 2 for warehouse mapping
- **Video / camera runtime** — MJPEG proxy and recording hooks (`/video/*`), with sim UDP source support
- **Photogrammetry pipeline** — mapping job orchestration via Celery workers and optional WebODM integration
- **Geospatial tooling** — fields, geofences, mapping overlays (Google Maps, Cesium, MapLibre, Leaflet)
- **Operational modules** — alerts, fleet management, irrigation monitoring, livestock workflows, patrol/debug tooling
- **Integrations** — MQTT, OPC UA, S3-compatible storage (MinIO), webhooks, API keys
- **Backend API** — modular FastAPI service with OpenAPI docs at `/docs`
- **Frontend dashboard** — React + TypeScript + Vite operator console

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                     React / Vite Operator Dashboard                   │
│   mission-runtime · warehouse · photogrammetry · maps · dashboard   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP + WebSocket (Vite proxy in dev)
                                v
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend API                            │
│  modules/          domain APIs (missions, warehouse, telemetry, …)   │
│  infrastructure/   camera, messaging, persistence, vehicle adapters   │
│  core/             config, database, security, logging                │
│  entrypoints/      api app, Celery workers, CLI                       │
└───────┬───────────────┬────────────────┬────────────────────────────┘
        │               │                │
        v               v                v
 PostgreSQL/PostGIS   Redis + Celery    MinIO / S3
 (missions, maps,     (photogrammetry,   (mapping assets,
  telemetry, etc.)     exports, etc.)     signed downloads)
        │
        │ optional
        v
┌─────────────────────────────────────────────────────────────────────┐
│              ROS 2 / Gazebo (warehouse simulation)                  │
│  ros2_ws/drone_gz_bridge  →  PointCloud2 / RGB-D / IMU / odom       │
│  live-map bridges         →  chunked ingest + WS stream to frontend   │
└─────────────────────────────────────────────────────────────────────┘
        │
        v
 MAVLink runtime (DroneKit / pymavlink) · sim video UDP · MQTT / OPC UA
```

**Data flow (simplified):**

1. The frontend calls REST endpoints and opens WebSocket channels for telemetry and live maps.
2. Mission execution runs in the API process (async) and publishes events through the telemetry manager.
3. Warehouse scans subscribe to ROS topics, encode point clouds into chunks, and stream them to clients.
4. Heavy photogrammetry and export work is offloaded to Celery workers.

---

## Repository Structure

```text
backend/
├── core/                 # Settings, database session, security, logging
├── modules/              # Domain modules (missions, warehouse, telemetry, mapping, …)
├── infrastructure/       # Camera, messaging, persistence, vehicle, photogrammetry adapters
├── entrypoints/
│   ├── api/              # FastAPI application entrypoint
│   ├── workers/          # Celery worker tasks
│   └── cli/              # CLI utilities (e.g. run_mission)
├── infrastructure/persistence/alembic/   # Database migrations
├── tests/                # Backend pytest suite
├── scripts/              # Lint baselines, guardrails, helper scripts
├── storage/              # Local runtime storage (logs, live-map chunks, captures)
└── .env.example          # Backend environment template

frontend/
├── src/
│   ├── app/              # Routing and app shell
│   ├── modules/          # Feature modules (warehouse, mission-runtime, maps, …)
│   └── shared/           # Shared UI, theme, utilities
├── e2e/                  # Playwright end-to-end tests
└── .env.example          # Frontend environment template

ros2_ws/
└── src/drone_gz_bridge/  # Gazebo ↔ ROS 2 bridge config and launch files

docker-compose.yml        # Postgres, Redis, MinIO, API, workers, frontend
Makefile                  # Quality checks, tests, local-dev entrypoint
Makefile.local            # Honcho-based local development
Procfile.dev              # Processes for make local-dev
pyproject.toml            # Ruff / mypy / pytest configuration
requirements.txt          # Python dependencies (includes ROS-related packages)
```

Backend code follows a layered layout enforced by `backend/scripts/check_backend_boundaries.py`: domain APIs live in `modules/`, integrations in `infrastructure/`, and workers stay thin in `entrypoints/workers/`.

---

## Requirements

### Required for core development

| Component | Version / notes |
|-----------|-----------------|
| Python | **3.11** (see `pyproject.toml`, `backend/Dockerfile`) |
| Node.js | **22** recommended (see `frontend/Dockerfile`; newer LTS may work) |
| npm | Bundled with Node.js |
| PostgreSQL + PostGIS | Required for the API and migrations |
| Redis | Required for Celery and runtime caching |
| `redis-server` | Must be installed locally for `make start` (Procfile starts it on port **6380**) |
| `honcho` | Process manager for local dev (`pip install honcho`) |

### Optional / feature-specific

| Component | Used for |
|-----------|----------|
| Docker + Docker Compose | Full-stack containerized dev |
| MinIO or S3-compatible storage | Mapping asset storage (`STORAGE_BACKEND=s3`) |
| ROS 2 Jazzy + Gazebo Sim | Warehouse simulation and live 3D mapping |
| nvBlox | Optional warehouse mapping layers (see warehouse live-map docs) |
| WebODM | External photogrammetry processing |
| MQTT broker (`mosquitto`) | MQTT integrations (commented out in `Procfile.dev`) |
| GDAL / mesh tooling | Photogrammetry worker outputs (see `backend/entrypoints/workers/README.md`) |
| MAVLink-compatible vehicle or SITL | Live drone telemetry and command paths |

---

## Environment Setup

Copy the example files and adjust values for your machine:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

### Backend (`backend/.env`)

Key variables (see `backend/.env.example` for the full list):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL/PostGIS connection (`postgresql+asyncpg://…`) |
| `JWT_SECRET` | Auth token signing |
| `SETTINGS_VAULT_KEY` | Encrypts sensitive settings at rest |
| `REDIS_URL` / `CELERY_BROKER_URL` | Redis for cache and Celery |
| `DRONE_CONN` | MAVLink connection string |
| `S3_*` / `STORAGE_BACKEND` | Object storage configuration |
| `WEBODM_*` | Photogrammetry integration (`WEBODM_MOCK_MODE=1` for local mock) |
| `ROS_DOMAIN_ID` | Must match your ROS 2 shell / simulation |
| `WAREHOUSE_*` | Warehouse bridge, capture paths, live-map ingest |
| `DRONE_VIDEO_*` | Sim or hardware video source |

Generate a vault key:

```bash
python -c "from backend.core.security.secrets import Vault; print(Vault.generate_key())"
```

### Frontend (`frontend/.env`)

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Leave **unset** for local dev so Vite proxies API calls and cookies stay same-origin |
| `VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY` | Google Maps |
| `VITE_GOOGLE_MAPS_MAP_ID` | Google Maps map ID |
| `VITE_CESIUM_ION_TOKEN` | Cesium globe token |

Do not commit real secrets. Replace all placeholder values before any shared or production deployment.

---

## Installation

### 1. Clone and enter the repository

```bash
git clone <repo-url>
cd drone_app
```

### 2. Backend

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install honcho
```

### 3. Frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Database migrations

Ensure PostgreSQL is running and `DATABASE_URL` in `backend/.env` is correct, then:

```bash
alembic -c backend/alembic.ini upgrade head
```

### 5. Docker Compose (alternative)

Build and start the full containerized stack:

```bash
docker compose up --build
```

This starts Postgres, Redis, MinIO, API, Celery worker/beat, and the production-built frontend.

---

## Running Locally

### Recommended: Honcho dev stack

```bash
make start
# equivalent to: make local-dev
```

This uses `Procfile.dev` to start:

- Redis on `127.0.0.1:6380`
- FastAPI backend on `http://localhost:8000`
- Vite frontend on `http://localhost:5173`

Open the dashboard at **http://localhost:5173**. API docs: **http://localhost:8000/docs**.

`make local-dev` does **not** start PostgreSQL. Run it separately, for example:

```bash
docker compose up -d postgres
```

Or point `DATABASE_URL` at an existing PostGIS instance.

### Manual startup

```bash
# Terminal 1 — Redis (if not using Procfile)
redis-server --port 6380

# Terminal 2 — Backend
source .venv/bin/activate
alembic -c backend/alembic.ini upgrade head
uvicorn backend.entrypoints.api.app:app --reload --host localhost --port 8000

# Terminal 3 — Frontend
cd frontend && npm run dev
```

### Optional Celery workers

`Procfile.dev` defines worker processes but they are not started by default. Run them when testing photogrammetry, exports, or warehouse-mapping queues:

```bash
honcho -f Procfile.dev start photogrammetry_worker
```

### Docker Compose URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:8080 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |

### Cleanup

```bash
make kill-dev      # stop Honcho / uvicorn / local Redis
make kill-workers  # stop Celery workers
make reset-dev     # kill processes and clear frontend Vite cache
```

---

## Running Tests

### Backend

```bash
make backend-tests              # unit tests (excludes integration marker)
make backend-integration-tests  # tests marked @pytest.mark.integration
make backend-quality            # ruff baseline + guardrails + mypy + unit tests
```

Run pytest directly:

```bash
python -m pytest backend/tests -m "not integration"
```

### Frontend

```bash
make frontend-tests    # vitest
make frontend-e2e      # Playwright (installs Chromium first)
make frontend-quality  # eslint baseline + arch checks + production build
```

### Full repo checks

```bash
make check          # backend-quality + frontend biome/tsc checks
make fix            # auto-fix ruff + biome where possible
make commit-ready   # fix + check
```

---

## Main Workflows

### Warehouse scan mission

1. Open the **Warehouse** page in the dashboard.
2. Run preflight checks (`GET/POST /warehouse/preflight`).
3. Start a scan (`POST /warehouse/missions/start`).
4. The backend creates a mission, runs `WarehouseScanMission`, warms ROS/nvBlox topics when configured, and starts live-map bridges.
5. The frontend subscribes to mission telemetry and opens the live voxel map WebSocket once a `flight_id` is active.

See `flight_flow.txt` and `backend/modules/warehouse/docs/live-map-validation.md` for the traced call chain and ROS validation commands.

### Live telemetry

1. Authenticate via `/auth/*` (session cookies in the browser).
2. Connect to `ws://localhost:8000/ws/telemetry` (proxied as `/ws/telemetry` through Vite).
3. Mission lifecycle events and runtime updates are broadcast through `telemetry_manager`.

### Live 3D mapping

1. ROS bridges publish `PointCloud2` topics (e.g. `/warehouse/front/rgbd/points`).
2. Backend live-map bridges encode chunks and expose:
   - `POST /warehouse/live-map/{flight_id}/chunks/{chunk_id}`
   - `GET /warehouse/live-map/{flight_id}/chunks/{chunk_id}/download`
   - `WS /warehouse/live-map/{flight_id}/stream`
3. The frontend `WarehouseLiveVoxelMapViewer` decodes chunks and renders layers in Three.js.

### Video / camera

1. Configure `DRONE_VIDEO_SOURCE_SIM` or hardware source in `backend/.env`.
2. Start the stream via `POST /video/start`.
3. View MJPEG at `/video/mjpeg` (used by `useMissionVideo` on mission pages).

### Persistence and replay

- Scan artifacts land under `backend/storage/warehouse-live-map/` and related capture directories.
- Scanned maps are listed via `GET /warehouse/scanned-maps`.
- Replay snapshots: `GET /warehouse/scanned-maps/{job_id}/live-map-snapshot`.

---

## API Overview

Interactive docs: **http://localhost:8000/docs**

| Area | Prefix / path | Notes |
|------|---------------|-------|
| Auth | `/auth/*` | Login, session cookies, OIDC hooks |
| Missions / tasks | `/tasks/*` | Mission CRUD, preflight, grid preview, commands |
| Telemetry | `/telemetry/*`, `/runtime/*` | Telemetry control and runtime status |
| WebSockets | `/ws/telemetry` | Live mission/vehicle events |
| Warehouse | `/warehouse/*` | Maps, docks, scans, live map, flight control |
| Live map | `/warehouse/live-map/*` | Chunk ingest, diagnostics, WebSocket stream |
| Video | `/video/*` | Stream start/stop, MJPEG proxy |
| Mapping | `/mapping/*` | Photogrammetry jobs and assets |
| Fields / geofences | `/fields/*`, `/geofences/*` | Field registry and fences |
| Alerts / settings | `/api/alerts`, `/api/settings` | Operational alerts and runtime settings |
| Integrations | `/integrations/*`, `/tasks/webhooks/*` | Webhooks and external hooks |
| Health | `/health`, `/healthz` | Liveness checks |

Admin, fleet, irrigation, livestock, analytics, and patrol-debug routes are also registered in `backend/entrypoints/api/app.py`.

---

## Development Notes

### Coding conventions

- **Python 3.11**, formatted and linted with **Ruff**; type-checked with **mypy** baselines (`backend/scripts/`).
- **Frontend**: TypeScript, ESLint baselines, Vitest for unit tests, Playwright for e2e.
- Import boundaries between `modules/`, `infrastructure/`, and `entrypoints/` are enforced in CI-style guardrails (`make backend-guardrails`).
- File-size baselines exist for both backend and frontend to limit module growth.

### Adding a backend module

1. Create a package under `backend/modules/<name>/`.
2. Expose an `APIRouter` from `api.py`.
3. Register the router in `backend/entrypoints/api/app.py`.
4. Add repositories/models under the module; keep SQLAlchemy details out of thin API layers.
5. Add tests under `backend/tests/`.

### Logs

Runtime logs are written under `backend/storage/logs/` (configurable via `DRONE_RUNTIME_LOG_ROOT`). Check the API process output when running via Honcho or uvicorn.

### ROS / Gazebo topics

- Bridge config: `ros2_ws/src/drone_gz_bridge/config/warehouse_bridge.yaml`
- Launch files: `ros2_ws/src/drone_gz_bridge/launch/`
- Set `ROS_DOMAIN_ID` consistently in `backend/.env` and your ROS shell.
- Verify topics after launching the bridge:

```bash
ros2 topic list
ros2 topic hz /warehouse/front/rgbd/points
```

- Live-map layer mapping and diagnostics: `backend/modules/warehouse/docs/live-map-validation.md`

### Photogrammetry workers

See `backend/entrypoints/workers/README.md` for queue names, required binaries, and WebODM configuration.

---

## Troubleshooting

| Symptom | Things to check |
|---------|-----------------|
| Backend won't start | `DATABASE_URL` reachable? Migrations applied? Port 8000 free? Run `make kill-dev` and retry. |
| Redis unavailable | Local dev expects `redis-server` on port **6380**. Docker Compose uses **6379**. Align `REDIS_URL`. |
| Frontend can't reach API | Leave `VITE_API_BASE_URL` unset in local dev. Confirm Vite proxy targets port 8000. |
| Login works but dashboard fails | Cross-origin cookies — do not set `VITE_API_BASE_URL=http://localhost:8000` during local dev. |
| PostgreSQL connection errors | Start Postgres (`docker compose up -d postgres`) or fix credentials in `backend/.env`. |
| ROS / Gazebo topics missing | Bridge running? `ROS_DOMAIN_ID` matches? Gazebo world `iris_warehouse` launched? |
| Video stream unavailable | `DRONE_VIDEO_USE_SIM=1` and UDP source running? Check `POST /video/start` response and `/video/mjpeg`. |
| Live map chunks not loading | Preflight / mapping stack status (`/warehouse/mapping-stack/status`). ROS topics publishing? WS auth cookie present? |
| Celery jobs stuck | Redis up? Start the relevant worker from `Procfile.dev`. Check `CELERY_BROKER_URL`. |

---

## Project Status

This repository is an **active development** platform. The backend architecture, frontend modules, warehouse live-mapping pipeline, and Docker Compose baseline are in place, but:

- Hardware MAVLink, ROS 2, and Gazebo paths need target-environment validation.
- WebODM, MQTT, OPC UA, and S3 integrations depend on external services.
- Some domain workflows (irrigation analytics, patrol ML, multi-drone coordination) are partial or experimental.
- A project license has not been added yet.

Treat flight and mapping features as **experimental** until validated in simulation and on your specific airframe.

---

## License and Contribution

**License:** not specified.

Contributions are welcome. Run `make commit-ready` before opening a pull request. Keep changes focused, match existing module boundaries, and add tests when behavior changes.

---

## Security Notes

- Replace all development secrets before deployment.
- Use HTTPS and secure cookies in production (`COOKIE_SECURE=1`).
- Validate flight safety in simulation before real hardware flights.
- Review CORS, auth, and API-key settings before exposing the API publicly.
