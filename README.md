# Drone Operations Platform

A full-stack drone mission control platform with a FastAPI backend, React operator dashboard, Celery workers, geospatial tooling, and optional ROS 2 / Gazebo simulation support.

## Overview

Drone Operations Platform is a work-in-progress application for planning, monitoring, and reviewing drone operations. It combines a Python backend API, a TypeScript operator console, background workers, database persistence, mapping workflows, and optional simulation bridges for warehouse-style indoor mapping.

The project is intended for development and experimentation around:

- Mission planning and runtime monitoring
- Telemetry and video workflows
- Warehouse scan and live-map pipelines
- Photogrammetry job orchestration
- Geospatial field, geofence, and patrol workflows
- Operational observability for API and worker processes

This repository is not a drop-in autopilot product. Real aircraft, robotics, ROS/Gazebo, WebODM, MQTT, OPC UA, and object storage integrations require environment-specific setup and validation.

## Key Features

- **FastAPI backend** with modular routers for authentication, missions, telemetry, warehouse operations, mapping, fields, geofences, alerts, fleet, integrations, video analysis, and observability.
- **React operator dashboard** built with TypeScript, Vite, Material UI, React Router, React Query, Cesium, MapLibre, Leaflet, Google Maps integrations, and Three.js-based mapping views.
- **Mission and telemetry runtime** with REST endpoints, WebSocket telemetry, MAVLink connection settings, runtime health endpoints, and mission command paths.
- **Warehouse scan workflows** for maps, docks, scan targets, preflight runs, mapping-stack status, manual mapping, live-map chunk ingest, and live-map WebSocket streaming.
- **Photogrammetry pipeline** using Celery queues, Redis, optional WebODM integration, mapping asset storage, and worker deployment notes.
- **Video and camera runtime** with stream start/status endpoints, MJPEG proxy support, recording hooks, and video-analysis job APIs.
- **Geospatial modules** for fields, geofences, mapping jobs, patrol templates, route previews, and integration exports.
- **Observability support** with OpenTelemetry, Prometheus metrics, Grafana/Tempo local stack configuration, structured logs, and an Observability page in the UI.
- **Quality gates** for backend boundaries, file-size guardrails, Ruff, mypy baselines, frontend linting, Vitest, and Playwright.

## Architecture

The repository is organized as a layered full-stack system:

- `backend/entrypoints` starts the FastAPI app, Celery workers, and CLI tools.
- `backend/modules` contains domain-facing APIs and application logic.
- `backend/infrastructure` contains adapters for persistence, vehicle/runtime integrations, camera/video, messaging, photogrammetry, storage, warehouse bridge helpers, and external services.
- `backend/core` contains cross-cutting configuration, database sessions, logging, security, events, and error handling.
- `frontend/src/app` defines routing and providers.
- `frontend/src/modules` contains UI feature modules that call backend APIs through shared clients.
- `ros2_ws/src/drone_gz_bridge` contains optional ROS 2 / Gazebo bridge configuration and launch files for warehouse simulation.

```mermaid
flowchart TD
  Operator[Operator Browser] --> Frontend[React + Vite Dashboard]
  Frontend -->|REST via Vite proxy| API[FastAPI Backend]
  Frontend -->|WebSockets| API

  API --> Modules[Backend Domain Modules]
  Modules --> Core[Core Config, DB, Security, Logging]
  Modules --> Infra[Infrastructure Adapters]

  Core --> Postgres[(PostgreSQL / PostGIS)]
  API --> Redis[(Redis)]
  Redis --> Workers[Celery Workers]
  Workers --> Storage[Local Storage / MinIO / S3]
  Modules --> Storage

  Infra --> MAVLink[MAVLink / DroneKit / pymavlink]
  Infra --> MQTT[MQTT]
  Infra --> OPCUA[OPC UA]
  Infra --> WebODM[Optional WebODM]

  ROS[ROS 2 / Gazebo Bridge] --> API
  API --> Observability[Prometheus / OpenTelemetry / Grafana / Tempo]
```

### Runtime Flow

1. The frontend serves the operator dashboard and proxies API, WebSocket, and asset requests to the backend during local development.
2. The FastAPI app registers routers from `backend/modules/*`, initializes the database, runtime settings, alert engine, irrigation monitor, logging, metrics, and tracing.
3. Mission, warehouse, video, mapping, patrol, telemetry, and integration modules coordinate through repositories and infrastructure adapters.
4. Redis backs Celery workers for heavier asynchronous jobs such as photogrammetry, exports, webhooks, video analysis, and warehouse mapping tasks.
5. Optional ROS 2 / Gazebo bridge processes publish simulation topics that warehouse mapping code can consume for live-map workflows.

## Tech Stack

### Backend

- Python 3.11
- FastAPI, Uvicorn
- Pydantic and pydantic-settings
- SQLAlchemy, Alembic, asyncpg, GeoAlchemy2
- Celery, Redis
- DroneKit, pymavlink
- OpenCV, NumPy, SciPy, PyTorch, Ultralytics, Supervision
- OpenTelemetry, Prometheus client, Sentry SDK
- MQTT via `paho-mqtt`
- OPC UA via `asyncua` / `opcua`
- S3-compatible storage via aiobotocore

### Frontend

- React 19, TypeScript, Vite
- React Router
- TanStack React Query
- Material UI, MUI X components
- Cesium / Resium
- MapLibre GL, Leaflet, Google Maps
- Three.js, React Three Fiber, Drei
- Vitest, Testing Library, Playwright
- ESLint, Biome, TypeScript compiler

### Data, Infrastructure, and Simulation

- PostgreSQL with PostGIS
- Redis
- MinIO or S3-compatible object storage
- Docker and Docker Compose
- ROS 2 Jazzy / Gazebo Sim bridge package under `ros2_ws`
- Optional nvBlox launch support
- Optional Grafana, Prometheus, and Tempo stack

## Repository Structure

```text
.
backend/
  core/                         # Settings, database, logging, events, security, errors
  entrypoints/
    api/app.py                  # FastAPI application and router registration
    cli/                        # CLI entrypoints
    workers/                    # Celery app and worker task modules
  infrastructure/               # Adapters for AI, camera, mapping, storage, messaging, vehicle, warehouse
  modules/                      # Domain modules and API routers
  infrastructure/persistence/
    alembic/                    # Alembic migrations
  scripts/                      # Quality gates and baseline checks
  tests/                        # Backend pytest suite
  .env.example                  # Backend environment template
  requirements.txt              # Backend Python dependencies
frontend/
  src/app/                      # React app shell, routing, providers, config
  src/modules/                  # Feature modules and views
  src/shared/                   # Shared API client, layout, UI, theme, hooks, utilities
  e2e/                          # Playwright tests
  package.json                  # Frontend dependencies and scripts
  .env.example                  # Frontend environment template
ros2_ws/src/drone_gz_bridge/    # ROS 2 / Gazebo bridge package for warehouse simulation
docs/                           # Observability and property-patrol documentation
infra/observability/            # Grafana, Prometheus, and Tempo configuration
docker-compose.yml              # App, PostGIS, Redis, MinIO, workers, frontend
docker-compose.observability.yml # Optional observability stack
Makefile                        # Top-level quality and dev commands
Makefile.local                  # Honcho-based local workflow
Procfile.dev                    # Local process definitions
pyproject.toml                  # Ruff, mypy, pytest, vulture config
pytest.ini                      # Pytest path configuration
```

## Getting Started

### Prerequisites

Core development:

- Python 3.11
- Node.js 22 and npm
- PostgreSQL with PostGIS
- Redis
- `honcho` for the local multi-process workflow

Optional, depending on the workflow:

- Docker and Docker Compose
- MinIO or another S3-compatible object store
- ROS 2 Jazzy and Gazebo Sim
- nvBlox for richer warehouse mapping experiments
- WebODM for external photogrammetry processing
- GDAL and mesh conversion tools for production photogrammetry workers
- MAVLink-compatible simulator or vehicle for live command paths
- Grafana, Prometheus, and Tempo for observability

### 1. Clone the Repository

```bash
git clone <repo-url>
cd drone_app
```

### 2. Configure Environment Files

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Generate a backend settings vault key:

```bash
python -c "from backend.core.security.secrets import Vault; print(Vault.generate_key())"
```

Place the generated value in `backend/.env` as `SETTINGS_VAULT_KEY`.

### 3. Install Backend Dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m pip install honcho
```

### 4. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 5. Start Required Local Services

For local development without the full Docker stack, start PostgreSQL/PostGIS separately. One option is to run only the Compose database:

```bash
docker compose up -d postgres
```

The Honcho workflow starts a local Redis process on port `6380`, but you can also run Redis yourself if needed.

### 6. Run Database Migrations

Ensure `DATABASE_URL` in `backend/.env` points to your PostGIS database, then run:

```bash
source .venv/bin/activate
python -m alembic -c backend/alembic.ini upgrade head
```

### 7. Run the App Locally

```bash
make start
```

This delegates to `make local-dev` and starts the processes defined in `Procfile.dev`:

- Redis on `127.0.0.1:6380`
- FastAPI on `http://localhost:8000`
- Vite frontend on `http://localhost:5173`

Useful URLs:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health` and `http://localhost:8000/healthz`
- Metrics, when enabled: `http://localhost:8000/metrics`

### Manual Startup

```bash
# Terminal 1
redis-server --port 6380

# Terminal 2
source .venv/bin/activate
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn backend.entrypoints.api.app:app --reload --host localhost --port 8000

# Terminal 3
cd frontend
npm run dev
```

### Docker Setup

`docker-compose.yml` defines PostgreSQL/PostGIS, Redis, MinIO, the API, a Celery worker, Celery beat, and a production-built frontend.

```bash
docker compose up --build
```

Container URLs:

| Service | URL |
| --- | --- |
| API | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| Frontend | `http://localhost:8080` |
| MinIO console | `http://localhost:9001` |

TODO: `backend/Dockerfile` currently copies `requirements.txt` from the repository root, while this repository contains `backend/requirements.txt`. Confirm or update the Dockerfile before relying on a fresh container build.

### Optional Observability Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile observability up -d
```

| Service | URL |
| --- | --- |
| Grafana | `http://localhost:3000` |
| Prometheus | `http://localhost:9090` |
| Tempo | `http://localhost:3200` |

See `docs/local-observability.md` and `docs/observability.md` for details.

## Configuration

Use placeholders for local development and real secret values only in private environment files or a secrets manager.

### Backend Environment Variables

| Variable | Description | Required | Example |
| --- | --- | --- | --- |
| `DATABASE_URL` | Async SQLAlchemy URL for PostgreSQL/PostGIS. | Yes | `postgresql+asyncpg://drone:change-me@localhost:5432/drone` |
| `SETTINGS_VAULT_KEY` | Encryption key for sensitive runtime settings. | Yes | `<generated-fernet-key>` |
| `JWT_SECRET` | Secret for signing application auth tokens. | Yes | `<long-random-secret>` |
| `ADMIN_EMAILS` | Comma-separated admin user emails. | Optional | `admin@example.com` |
| `GOOGLE_MAPS_API_KEY` | Google Maps API key for geospatial workflows. | Optional | `<google-maps-key>` |
| `LLM_PROVIDER` | Local or OpenAI-compatible LLM provider selector. | Optional | `ollama` |
| `LLM_API_BASE` | LLM provider API base URL. | Optional | `http://localhost:11434/api/generate` |
| `LLM_MODEL` | Default LLM model name. | Optional | `deepseek-r1:8b` |
| `DRONE_CONN` | MAVLink connection string for the main runtime. | Optional for UI-only dev | `udp:127.0.0.1:14550` |
| `DRONE_CONN_MAVPROXY` | MAVProxy-compatible MAVLink connection string. | Optional | `udp:127.0.0.1:14551` |
| `HEARTBEAT_TIMEOUT` | Vehicle heartbeat timeout in seconds. | Optional | `5.0` |
| `REDIS_URL` | Redis URL for runtime cache and services. | Optional | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker URL. | Optional unless workers run | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend URL. | Optional | `redis://localhost:6379/0` |
| `MAPPING_JOB_QUEUE_BACKEND` | Mapping job queue backend. | Optional | `celery` |
| `WEBODM_BASE_URL` | WebODM server URL. | Optional | `http://localhost:8001` |
| `WEBODM_API_TOKEN` | WebODM API token. | Optional | `<webodm-token>` |
| `WEBODM_MOCK_MODE` | Use mocked WebODM outputs for local development. | Optional | `1` |
| `STORAGE_BACKEND` | Asset storage backend. | Optional | `local` or `s3` |
| `S3_ENDPOINT_URL` | S3-compatible endpoint, such as MinIO. | Optional | `http://localhost:9000` |
| `S3_ACCESS_KEY` | S3 access key. | Optional | `<access-key>` |
| `S3_SECRET_KEY` | S3 secret key. | Optional | `<secret-key>` |
| `S3_BUCKET_NAME` | Bucket for mapping and deliverable assets. | Optional | `drone-assets` |
| `MQTT_BROKER` | MQTT broker hostname. | Optional | `127.0.0.1` |
| `MQTT_PORT` | MQTT broker port. | Optional | `1883` |
| `OPCUA_ENDPOINT` | OPC UA endpoint for industrial integrations. | Optional | `opc.tcp://0.0.0.0:4840/freeopcua/server/` |
| `RASPBERRY_HOST` | Raspberry Pi camera host. | Optional | `raspberrypi.local` |
| `SSH_KEY_PATH` | SSH key path for Raspberry Pi operations. | Optional | `/run/secrets/id_rsa` |
| `DRONE_VIDEO_SOURCE_SIM` | Simulated video source URL. | Optional | `udp://127.0.0.1:5600` |
| `DRONE_VIDEO_USE_SIM` | Use simulated video source. | Optional | `0` |
| `ROS_DOMAIN_ID` | ROS 2 domain used by the backend and ROS shell. | Optional | `0` |
| `WAREHOUSE_SIM_MODE` | Enable warehouse simulation behavior. | Optional | `0` |
| `WAREHOUSE_ROS2_WS` | ROS 2 workspace path. | Optional | `ros2_ws` |
| `WAREHOUSE_LIVE_MAP_INGEST_TOKEN` | Token for live-map ingest endpoints. | Optional for local dev | `dev-live-map-ingest` |
| `PHOTOGRAMMETRY_STORAGE_DIR` | Local path for mapping outputs. | Optional | `backend/storage/mapping` |
| `PHOTOGRAMMETRY_ASSET_SIGNING_SECRET` | Secret for signed mapping asset URLs. | Recommended when serving assets | `<dedicated-secret>` |
| `OBSERVABILITY_ENABLED` | Enable tracing and metrics integration. | Optional | `true` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint for traces. | Optional | `http://127.0.0.1:4318` |
| `PROMETHEUS_METRICS_ENABLED` | Enable Prometheus metrics endpoint. | Optional | `true` |
| `PROMETHEUS_METRICS_PATH` | Prometheus metrics path. | Optional | `/metrics` |

### Frontend Environment Variables

| Variable | Description | Required | Example |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | API base URL. Leave unset for local Vite proxy and same-origin cookies. | Optional | `http://localhost:8000` |
| `VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY` | Google Maps browser API key. | Optional | `<google-maps-key>` |
| `VITE_GOOGLE_MAPS_MAP_ID` | Google Maps map ID. | Optional | `<map-id>` |
| `VITE_CESIUM_ION_TOKEN` | Cesium Ion token. | Optional | `<cesium-token>` |

## Usage

### Operator Dashboard

Run the local dev stack, then open `http://localhost:5173`.

The router includes pages for:

- Dashboard home and insights
- Fleet
- Controlled flight
- Photogrammetry
- Field survey
- Warehouse
- Animal farm / livestock workflows
- Private patrol and property patrol
- Mission timeline
- Admin
- Templates and API keys
- Video analysis
- Observability
- Account and settings

### API Exploration

Open Swagger UI at:

```text
http://localhost:8000/docs
```

Common backend areas include:

| Area | Example routes |
| --- | --- |
| Health | `GET /health`, `GET /healthz` |
| Auth | `POST /signup`, `POST /login`, `POST /refresh`, `GET /me` |
| Missions | Routes registered from `backend/modules/missions/api/routes.py` |
| Telemetry | `POST /telemetry/connect`, `GET /telemetry/status`, `POST /telemetry/manual-control` |
| Runtime | `GET /runtime/status` |
| Telemetry WebSocket | `WS /ws/telemetry` |
| Warehouse | `GET /warehouse/maps`, `POST /warehouse/missions/start`, `GET /warehouse/preflight` |
| Warehouse live map | `GET /warehouse/live-map/config`, `WS /warehouse/live-map/{flight_id}/stream` |
| Mapping jobs | `POST /mapping/jobs`, `GET /mapping/jobs`, `POST /mapping/jobs/{job_id}/start` |
| Video | `POST /video/start`, `GET /video/status`, `GET /video/mjpeg` |
| Video analysis | `POST /video-analysis/videos`, `POST /video-analysis/videos/{video_id}/analyze` |
| Fields and geofences | `GET /fields`, `GET /geofences` |
| Property patrol | `POST /api/property-patrol/route-preview`, `POST /api/property-patrol/missions/start` |
| Observability | `GET /observability/status`, `GET /observability/links` |

### Example API Requests

```bash
curl http://localhost:8000/health
curl http://localhost:8000/healthz
curl http://localhost:8000/observability/status
curl http://localhost:8000/warehouse/live-map/config
```

Authenticated routes require browser session cookies or an API flow configured through the auth module.

### Warehouse Simulation Workflow

1. Configure `ROS_DOMAIN_ID`, warehouse environment variables, and ROS 2 shell consistently.
2. Build and source the ROS workspace if using the bridge:

   ```bash
   cd ros2_ws
   colcon build --symlink-install --packages-select drone_gz_bridge
   source install/setup.bash
   ```

3. Launch the Gazebo to ROS bridge from the `drone_gz_bridge` package.
4. Verify topics such as `/warehouse/front/rgbd/points`, `/warehouse/mid360/points`, `/warehouse/imu`, and `/warehouse/drone/odometry`.
5. Start the backend and frontend.
6. Use the Warehouse page to run preflight checks, start mapping stack actions, and inspect live-map diagnostics.

### Photogrammetry Workflow

1. Configure Redis and Celery variables.
2. Configure `WEBODM_*` values or use `WEBODM_MOCK_MODE=1` for local development.
3. Start a worker for the photogrammetry queue:

   ```bash
   celery -A backend.entrypoints.workers.celery_app:celery_app worker \
     --loglevel=INFO \
     --queues=photogrammetry \
     --hostname=photogrammetry@%h
   ```

Warehouse structure extraction also requires Redis plus a worker consuming the
`warehouse_mapping` queue. Restart that worker after task-module changes. Use
`GET /readiness` to verify the API can reach the configured Redis broker.

4. Use mapping endpoints or the Photogrammetry dashboard page to create/upload/start jobs.

See `backend/entrypoints/workers/README.md` for worker topology and required production tools.

## Testing

### Backend Tests

```bash
python -m pip install -r backend/requirements-dev.txt
make backend-tests
make backend-test-env-up
make backend-integration-tests
```

Direct pytest command:

```bash
python backend/scripts/run_backend_tests.py --skip-migrations
python backend/scripts/run_backend_tests.py --integration --wait-db
```

Backend tests are written with pytest and include coverage for flight profiles, warehouse live maps, observability, local runtime setup, point-cloud parsing, property patrol, and worker tasks.
The test runner loads `backend/test.env.example`, disables third-party pytest plugin autoload, and explicitly loads `pytest-asyncio` from `backend/tests/conftest.py`. This keeps ROS pytest plugins from affecting normal backend runs while still supporting async tests. Integration tests expect PostgreSQL/PostGIS and Redis; `make backend-test-env-up` starts those dependencies with `docker-compose.test.yml`.

### Frontend Tests

```bash
make frontend-tests
make frontend-e2e
```

Direct frontend commands:

```bash
cd frontend
npm run test
npm run test:e2e
```

Frontend tests use Vitest, Testing Library, and Playwright.

### Full Quality Checks

```bash
make check
make commit-ready
```

## Development Workflow

Useful commands:

| Command | Purpose |
| --- | --- |
| `make start` | Start the local Honcho dev stack. |
| `make local-dev-no-observability` | Start local dev with observability disabled. |
| `make warehouse` | Start the warehouse-focused local process set. |
| `make fix` | Run Ruff fixes/formatting and Biome fixes. |
| `make check` | Run backend quality checks, frontend Biome check, and TypeScript check. |
| `make backend-quality` | Run backend lint, typecheck, guardrails, and non-integration tests. |
| `make backend-test-env-up` | Start PostgreSQL/PostGIS, Redis, and MinIO for backend integration tests. |
| `make backend-test-env-down` | Stop and remove backend integration-test service state. |
| `make backend-guardrails` | Run backend file-size, boundary, mypy, and test checks. |
| `make frontend-quality` | Run frontend lint baseline, architecture check, and production build. |
| `make frontend-tests` | Run Vitest. |
| `make frontend-e2e` | Install Playwright Chromium and run e2e tests. |
| `make kill-dev` | Stop local Honcho, uvicorn, Redis, and occupied dev ports. |
| `make reset-dev` | Stop dev processes and clear Vite cache. |

Backend conventions:

- Keep API registration in `backend/entrypoints/api/app.py`.
- Keep domain features under `backend/modules/<feature>`.
- Keep external integrations and infrastructure details under `backend/infrastructure`.
- Use Alembic for schema changes.
- Respect boundary and file-size guardrails in `backend/scripts`.

Frontend conventions:

- Add routes in `frontend/src/app/routes/AppRouter.tsx`.
- Keep feature code under `frontend/src/modules/<feature>`.
- Use shared API, layout, UI, theme, hook, and utility code from `frontend/src/shared`.
- Keep tests close to the relevant module when possible.

## Roadmap

### Completed or Present in the Repository

- Modular FastAPI app with registered domain routers.
- React/Vite dashboard with protected routes and feature modules.
- PostgreSQL/PostGIS persistence with Alembic migrations.
- Redis/Celery worker setup for asynchronous jobs.
- Warehouse maps, preflight, scan targets, live-map endpoints, and frontend warehouse modules.
- Mission launch ownership and preflight paths: [docs/mission_launch_architecture.md](docs/mission_launch_architecture.md).
- Property patrol API and frontend route.
- Observability documentation and optional Grafana/Prometheus/Tempo Compose stack.
- Backend and frontend test suites plus quality guardrails.

### In Progress or Environment-Dependent

- Hardware MAVLink command paths and vehicle-specific validation.
- ROS 2 / Gazebo warehouse simulation workflow.
- nvBlox and live 3D warehouse mapping validation.
- Photogrammetry production worker toolchain and WebODM integration.
- Video AI model setup and production inference workflow.
- MQTT, OPC UA, S3/MinIO, and external webhook integrations.

### Future Ideas

- Add CI workflows for backend and frontend quality gates.
- Add a root license and clarify usage rights.
- Add production deployment documentation.
- Add architecture decision records for module boundaries and runtime patterns.
- Add screenshots or a short demo video for the operator dashboard.
- Add seed data or a scripted demo scenario for reviewers.

## Security and Safety Notes

- Do not commit real secrets, API keys, JWT secrets, S3 credentials, WebODM tokens, SSH keys, or vehicle credentials.
- Replace all development defaults before sharing or deploying the app.
- Use HTTPS, secure cookies, restricted CORS, strong JWT secrets, and private secret storage in production.
- Treat drone, robotics, video AI, automation, and mapping workflows as safety-critical.
- Validate every command path in simulation before connecting real hardware.
- Real-world drone operation requires competent supervision, failsafe planning, airspace awareness, and compliance with local aviation and privacy regulations.
- Sensor-triggered or AI-assisted workflows should remain operator-reviewed unless specifically validated for autonomous operation.

## Contributing

Contributions are welcome.

1. Create a focused branch.
2. Install backend and frontend dependencies.
3. Make a small, reviewable change.
4. Add or update tests when behavior changes.
5. Run the relevant quality checks:

   ```bash
   make commit-ready
   ```

6. Open a pull request with a clear summary, test evidence, and any setup notes.

Please keep module boundaries intact and avoid mixing unrelated refactors with feature changes.

## License

No license has been specified yet.

The ROS 2 package metadata under `ros2_ws/src/drone_gz_bridge/package.xml` declares `MIT`, but there is no repository-level license file. If this project is intended to be source-available with commercial restrictions, add a proper source-available or non-commercial license instead of describing it as open source.

## Contact

Maintainer contact is not documented in the root repository metadata yet.

- GitHub: `TODO: add GitHub profile or organization link`
- Email: `TODO: add public contact email if desired`
